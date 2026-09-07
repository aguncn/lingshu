# 对话会话驱动服务（P8 agentscope-runtime，design D4）：每任务单活动 Session 的 park/continue 会话环 + SSE 事件桥。
# 运行模型：chat 请求线程持有一个 SSE 生成器，从 Session.msg_queue 阻塞读事件；每任务一个 worker 线程
#   在其私有 asyncio loop 里跑 agent.reply_stream()，把事件映射成 SSE JSON 推进 msg_queue；
#   遇到 RequireUserConfirmEvent（危险工具二次确认）就 park：广播 confirm_request 后停在该次 reply，
#   改从 decision_queue 取用户回执（经 POST /chat/decision 跨请求投递），收齐后以 UserConfirmResultEvent 续跑。
# 为什么线程+queue 而非同线程 await：Flask 是同步框架，而 reply_stream 是异步流式生成器，二者经
#   「worker 线程独占 loop + 线程安全队列」解耦（design D4）；决策经队列跨 HTTP 请求唤醒，无需同一条连接回写。
# 生命周期（保活版，session-keepalive）：SSE 断开 ≠ 取消 run——生成器被 close/异常只算「脱离」，
#   worker 继续把 run 跑完，并在 finally 里 push done/error *之后*自注销 unregister（同线程先后序），
#   覆盖「run 已结束但消费端早已脱离、没读到 done」的泄漏面；
#   读端在「读到终端帧自然结束」时也幂等 unregister（generate finally），保证结束后可立即再发起 chat，
#   不依赖 worker 调度时序（见 events() 的 _done_seen）；
#   停留待确认（park）且长时间无消费端刷新 → 后台 reaper 按 TTL 自动 cancel 并释放槽位（防永久 409）；
#   显式停止走 POST /tasks/<id>/chat/stop（cancel+join+unregister）；返回采纳/重显确认走 GET .../chat/status。
# 事件→SSE 映射（spec R2/R3）：TextBlockDelta→text_delta、ThinkingBlockDelta→thinking_delta、
#   ToolCall 结束→tool_call（名+参数）、ToolResult 结束→tool_result（名+成败+摘要）、
#   park→confirm_request、终端→done；模型解析失败/运行异常→error。密钥值绝不进任何事件。
import asyncio
import json
import queue
import threading
import time
import uuid

from . import audit as audit_svc
from . import mcp_client, message as message_svc
from .agent_runtime import build, require_deferred_clients
from .errors import AppError

# agentscope 事件/消息类惰性取回；缺失的事件类型容错为 None（版本漂移不致整模块崩）。
_event_objs = None


def _events() -> dict:
    global _event_objs
    if _event_objs is None:
        from agentscope import event as E
        from agentscope.message import UserMsg

        def _g(name):
            return getattr(E, name, None)

        _event_objs = {
            "UserMsg": UserMsg,
            "RequireUserConfirmEvent": _g("RequireUserConfirmEvent"),
            "UserConfirmResultEvent": _g("UserConfirmResultEvent"),
            "UserInterruptEvent": _g("UserInterruptEvent"),
            "ConfirmResult": _g("ConfirmResult"),
            "ReplyEndEvent": _g("ReplyEndEvent"),
            "TextBlockDeltaEvent": _g("TextBlockDeltaEvent"),
            "ThinkingBlockDeltaEvent": _g("ThinkingBlockDeltaEvent"),
            "ToolCallStartEvent": _g("ToolCallStartEvent"),
            "ToolCallDeltaEvent": _g("ToolCallDeltaEvent"),
            "ToolCallEndEvent": _g("ToolCallEndEvent"),
            "ToolResultStartEvent": _g("ToolResultStartEvent"),
            "ToolResultTextDeltaEvent": _g("ToolResultTextDeltaEvent"),
            "ToolResultEndEvent": _g("ToolResultEndEvent"),
            "ModelCallEndEvent": _g("ModelCallEndEvent"),
            "RequireExternalExecutionEvent": _g("RequireExternalExecutionEvent"),
        }
    return _event_objs


# SSE 参数/摘要截断上限：模型可能贴出超长参数或文件内容，防单事件撑爆行
_DETAIL_LIMIT = 1000
_RESULT_LIMIT = 2000
_POLL_INTERVAL = 0.05  # 决策等待轮询间隔（秒）：queue.Queue 跨线程非阻塞取 + 短暂让出

# 二次确认的固定提示语：confirm_request 事件与 /chat/status 重显确认复用同一文案，前端不用硬编码。
CONFIRM_REASON = "该内置写/执行类工具可能改动系统状态，需你确认放行"

# SSE 空闲保活：会话停驻（待确认/长思考）时无事件帧，若长时间零字节，网关/浏览器可能按空闲掐断长连接；
# 故 events() 每超过该间隔无帧就发一条 SSE 注释帧 ": ping"（前端解析器须跳过非 data: 行）。
_HEARTBEAT_SECONDS = 10.0
# park 回收 TTL：停留在「待用户回执」且消费端 beat 刷新超过该时长 → 视为无人认领的挂起确认，自动取消。
# 前台停留确认时消费端约每 0.5s 刷新 beat（events 读循环），绝无 10 分钟不刷新的前台场景；
# 后台跑着的 run 未 park 时不受此限（worker 跑完自注销）。TTL 只兜底「真没人看着」的 park，防 409 泄漏。
_CONSUMER_TTL = 600.0
# 孤儿回收守护线程的扫描间隔
_REAP_INTERVAL = 30.0


def _sse(**fields) -> str:
    """事件 dict → SSE 帧（UTF-8 JSON，`data:` 行 + 空行）。"""
    return "data: " + json.dumps(fields, ensure_ascii=False) + "\n\n"


class ChatSession:
    """一次 chat 运行的会话：agent + worker 线程/loop + 收发队列 + 确认注册表。"""

    def __init__(self, app, task_id: int, user_text: str):
        self.app = app
        self.task_id = task_id
        self.user_text = user_text
        self.run_id = uuid.uuid4().hex
        self.agent = None
        self.label = {}  # model 展示标签（无密钥），供消息 model 列 / 审计 target
        self.msg_queue: "queue.Queue[str]" = queue.Queue()  # worker → SSE 生成器
        self.decision_queue: "queue.Queue[dict]" = queue.Queue()  # 决策端点 → worker
        self.pending: dict = {}  # confirm_id → ToolCallBlock（尚未回执，single-use）
        self._cancelled = threading.Event()
        self._thread = None
        # —— 保活生命周期：消费端最近活跃时刻 + 是否已读到终端帧 ——
        self._last_consumer_seen = time.monotonic()  # events/status/decision 刷新，reaper 据此判孤儿
        self._done_seen = False  # events() 以「读到 done/error 终端帧」正常结束 → generate 收尾释放槽位
        self._connected_mcp: list = []
        # worker 侧运行缓冲
        self._assistant_text: list[str] = []
        self._tool_name: dict = {}
        self._tool_args: dict = {}
        self._tool_result_text: dict = {}
        self._tool_result_name: dict = {}
        # session-trace-ui：助手回合有序 trace 步骤 + 未闭合 thinking 缓冲（worker 单线程内累积）
        self._steps: list = []  # [{kind: thinking|confirm|tool_call|tool_result, ...}]，按事件完成序
        self._thinking: list = []  # 待归并的 thinking delta（连续思考归并为一块）

    # ---- 创建与启动 ----
    @classmethod
    def create(cls, app, task_id: int, user_text: str) -> "ChatSession":
        """在调用线程内解析模型并组 Agent；AppError（无模型/无密钥）向上抛，由 SSE 首事件转 error。

        为什么在此（而非 worker）解析/装配：模型不可用时需保证不产生任何对话副作用（spec R1），
        且装配需要 app 上下文；worker 启动前失败 = 直接 error 结束、不落消息。
        """
        sess = cls(app, task_id, user_text)
        agent, desc = build(task_id)
        sess.agent = agent
        sess.label = desc.get("model") or {}
        sess._deferred_clients = require_deferred_clients(desc)
        return sess

    def start(self) -> None:
        """spawn worker 线程：独占 asyncio loop 跑 _drive（asyncio.run 在子线程自动建/关 loop）。"""
        if self._thread is not None:
            return
        run_id = self.run_id

        def _worker():
            # worker 线程内所有 DB 访问（落助手文本/审计）需要独立 app 上下文
            with self.app.app_context():
                try:
                    asyncio.run(self._drive())
                except Exception as e:  # noqa: BLE001 —— 兜底：未捕获异常转 SSE error，绝不悬挂
                    if not self._cancelled.is_set():
                        self._push({"type": "error", "run_id": run_id, "message": f"运行异常：{e}"})
                finally:
                    # 正常跑完/异常都以 done 收尾，SSE 生成器据此结束；被取消则不打扰已断开的连接。
                    # 无论是否取消，都自注销释放注册表槽位：run 结束即让出，任务可再次发起 chat。
                    # 覆盖「worker 已跑完但消费端早已脱离、没读到 done」的泄漏面（detach 不清 cancel）。
                    if not self._cancelled.is_set():
                        self._push({"type": "done", "run_id": run_id})
                    unregister(self.task_id)

        self._thread = threading.Thread(
            target=_worker, name=f"ls-session-{self.task_id}", daemon=True
        )
        self._thread.start()

    # ---- worker 侧 ----
    async def _drive(self) -> None:
        """会话主循环：连接 deferred MCP → 首条用户消息 → park/continue 直至 ReplyEnd。"""
        ev = _events()
        ready = await mcp_client.connect_clients(getattr(self, "_deferred_clients", []))
        for client in ready:
            try:
                await mcp_client.attach_to_toolkit(self.agent.toolkit, client)
            except Exception:  # noqa: BLE001 —— attach 失败只丢该连接器，不阻断
                pass
        self._connected_mcp = ready

        ok = False
        try:
            inputs = ev["UserMsg"]("user", self.user_text)
            while not self._cancelled.is_set():
                parked = await self._run_once(inputs)
                if parked is None:
                    ok = True
                    break
                results = await self._await_decisions(parked)  # 该批全部回执；None=被中断
                if results is None:
                    return  # 中断路径：不落伪消息，finally 关 MCP
                inputs = ev["UserConfirmResultEvent"](
                    reply_id=parked.reply_id, confirm_results=results
                )
        finally:
            # MCP 生命周期收敛在 worker loop 内（connect/close 同 loop），LIFO close
            await mcp_client.close_clients(self._connected_mcp)
            self._connected_mcp = []

        # 成功跑完才落助手文本：以流上 text_delta 拼接的最终内容（spec「对话历史持久化」）
        if ok and not self._cancelled.is_set():
            full = "".join(self._assistant_text).strip()
            if full:
                self._close_thinking()  # run 结束：闭合可能残留的末尾 thinking 块
                trace = self._steps or None  # 纯文本回合 steps 为空 → None（to_dict 省略该字段）
                message_svc.add_assistant_message(
                    self.task_id, full, run_id=self.run_id,
                    model=self.label.get("model"), trace=trace,
                )

    async def _run_once(self, inputs):
        """跑一次 agent.reply_stream(inputs)：事件映射进 msg_queue；遇 RequireUserConfirmEvent 返回之。"""
        ev = _events()
        parked = None
        async for event in self.agent.reply_stream(inputs):
            if self._cancelled.is_set():
                return None  # 连接已断：放弃本次 reply（不写伪消息）
            if isinstance(event, ev["RequireUserConfirmEvent"]):
                parked = event
                continue  # park：流会在该事件后自然耗尽，此处只需记录
            if (
                ev["RequireExternalExecutionEvent"] is not None
                and isinstance(event, ev["RequireExternalExecutionEvent"])
            ):
                # design D4：无外部执行器，此事件不应出现；记审计并按拒绝处理，避免悬挂
                audit_svc.record(
                    task_id=self.task_id, run_id=self.run_id, actor="runtime",
                    action="tool_call", target="external", result="denied",
                    detail="RequireExternalExecutionEvent 不应出现（无外部执行器），按拒绝处理",
                )
                raise AppError("模型请求了本环境不支持的外部执行，已终止本次运行")
            if isinstance(event, ev["ReplyEndEvent"]):
                err = getattr(event, "error", None)
                if err:
                    raise AppError(f"模型调用失败：{err}")  # 由 worker 转 SSE error，不落助手消息
                continue
            self._map_event(event)
        return parked

    def _map_event(self, event) -> None:
        """单事件 → SSE JSON 并 push；同时累计文本与工具元数据供收尾持久化/审计。"""
        ev = _events()
        run_id = self.run_id

        # 助手文本增量：累计 + 实时推 text_delta
        if isinstance(event, ev["TextBlockDeltaEvent"]):
            delta = event.delta or ""
            self._assistant_text.append(delta)
            self._push({"type": "text_delta", "run_id": run_id, "delta": delta})
            return
        # 思考增量（DeepSeek reasoner 类模型）
        if ev["ThinkingBlockDeltaEvent"] is not None and isinstance(
            event, ev["ThinkingBlockDeltaEvent"]
        ):
            delta = event.delta or ""
            self._thinking.append(delta)  # 累计缓冲：归并为 thinking trace 步骤（_close_thinking 处闭合）
            self._push({"type": "thinking_delta", "run_id": run_id, "delta": delta})
            return
        # 工具调用开始：登记 id→name（后续事件多只带 tool_call_id）
        if isinstance(event, ev["ToolCallStartEvent"]):
            self._tool_name[event.tool_call_id] = getattr(event, "tool_call_name", "")
            self._tool_args[event.tool_call_id] = ""
            return
        # 工具参数增量（JSON 分片）：拼接为完整参数串
        if isinstance(event, ev["ToolCallDeltaEvent"]):
            self._tool_args[event.tool_call_id] = (
                self._tool_args.get(event.tool_call_id, "") + (event.delta or "")
            )
            return
        # 工具调用结束：参数齐备 → 推 tool_call（名+参数）+ 落 trace 步骤
        if isinstance(event, ev["ToolCallEndEvent"]):
            raw = self._tool_args.get(event.tool_call_id, "")
            try:
                arguments = json.loads(raw) if raw.strip() else {}
            except (ValueError, TypeError):
                arguments = raw[: _DETAIL_LIMIT]
            self._close_thinking()  # 先闭合悬挂 thinking，保证顺序（thinking 在调用前）
            self._steps.append({
                "kind": "tool_call",
                "name": self._tool_name.get(event.tool_call_id, ""),
                "args": arguments,
            })
            self._push({
                "type": "tool_call", "run_id": run_id,
                "name": self._tool_name.get(event.tool_call_id, ""),
                "arguments": arguments,
            })
            return
        # 工具结果开始：登记结果缓冲
        if isinstance(event, ev["ToolResultStartEvent"]):
            self._tool_result_text[event.tool_call_id] = ""
            self._tool_result_name[event.tool_call_id] = getattr(
                event, "tool_call_name", self._tool_name.get(event.tool_call_id, "")
            )
            return
        if isinstance(event, ev["ToolResultTextDeltaEvent"]):
            self._tool_result_text[event.tool_call_id] = (
                self._tool_result_text.get(event.tool_call_id, "") + (event.delta or "")
            )
            return
        # 工具结果结束：成败 + 摘要 → tool_result + 审计 tool_call
        if isinstance(event, ev["ToolResultEndEvent"]):
            tid = event.tool_call_id
            state = getattr(event, "state", "") or ""
            ok = state == "success"
            summary = (self._tool_result_text.get(tid, "") or "")[:_RESULT_LIMIT]
            tname = self._tool_result_name.get(tid) or self._tool_name.get(tid, "")
            self._close_thinking()
            self._steps.append({
                "kind": "tool_result", "name": tname, "ok": ok, "summary": summary,
            })
            self._push({
                "type": "tool_result", "run_id": run_id, "name": tname,
                "ok": ok, "summary": summary,
            })
            audit_svc.record(
                task_id=self.task_id, run_id=run_id, actor="runtime", action="tool_call",
                target=tname or "?", result="success" if ok else "error", detail=summary or None,
            )
            return
        # 单次模型调用结束：用量 → 审计 model_call（无密钥，target 为 provider/model）
        if isinstance(event, ev["ModelCallEndEvent"]):
            inp = getattr(event, "input_tokens", 0) or 0
            out = getattr(event, "output_tokens", 0) or 0
            target = f"{self.label.get('provider', '')}/{self.label.get('model', '')}".strip("/")
            audit_svc.record(
                task_id=self.task_id, run_id=self.run_id, actor="runtime",
                action="model_call", target=target or None, result="success",
                detail=f"in={inp} out={out}" if (inp or out) else None,
            )
            return

    # ---- session-trace-ui：trace 步骤构建 ----
    def _close_thinking(self) -> None:
        """把未闭合的 thinking 缓冲归并为一块 thinking 步骤；缓冲空则置空跳过。

        触发点：每 append 一个 confirm/tool 步骤之前、及 run 结束落 trace 前调用，
        保证连续思考块在 trace 里是单步、且排在随后的事件之前（worker 单线程内安全）。
        """
        text = "".join(self._thinking).strip()
        self._thinking = []
        if text:
            self._steps.append({"kind": "thinking", "text": text})

    def _record_confirm(self, name: str, allow: bool) -> None:
        """把一次二次确认决策落 trace：confirm 步骤带 decision。

        allow=放行后该工具才真正执行（trace 顺序恒为 tool_call→confirm→tool_result）；
        deny=拒绝则工具不产生任何写副作用，但 AgentScope 仍回 ok=false 的结果帧，
        故 trace 同样以 tool_call→confirm(deny)→tool_result(ok=false) 收尾，与 SSE 一致。
        """
        self._close_thinking()
        self._steps.append({
            "kind": "confirm", "name": name,
            "decision": "allow" if allow else "deny",
        })

    async def _await_decisions(self, parked) -> list | None:
        """注册并广播 confirm_request 后，等待该批全部回执；被取消返回 None。

        confirm_id = ToolCallBlock.id（全局唯一）；回执即从 pending 移除 → 同一 id 只可回执一次
        （spec R4 失效/已消费 confirm → 404，由决策端点依 pending 判定）。
        """
        ev = _events()
        # 先全部注册再广播：决策可在用户收到 confirm_request 前抢先到达也不至于 404
        for tc in parked.tool_calls:
            self.pending[tc.id] = tc
        for tc in parked.tool_calls:
            self._push({
                "type": "confirm_request", "run_id": self.run_id,
                "confirm_id": tc.id, "name": tc.name,
                "action": (tc.input or "")[:_DETAIL_LIMIT],  # 待确认动作摘要（截断），不入密钥
                "reason": CONFIRM_REASON,
            })
        results = []
        for tc in parked.tool_calls:
            while not self._cancelled.is_set():
                decision = self._poll_decision()
                if decision is None:
                    await asyncio.sleep(_POLL_INTERVAL)
                    continue
                if decision.get("confirm_id") != tc.id:
                    continue  # 同批其余确认的回执不打断当前等待
                self.pending.pop(tc.id, None)  # single-use：消费即失效
                allow = bool(decision.get("allow"))
                audit_svc.record(
                    task_id=self.task_id, run_id=self.run_id, actor="user",
                    action="confirm_decision", target=tc.id,
                    result="allow" if allow else "deny",
                    detail=f"工具 {tc.name} 用户{'放行' if allow else '拒绝'}",
                )
                self._record_confirm(tc.name, allow)  # trace：confirm 步骤（deny 亦回 ok=false 结果帧）
                results.append(ev["ConfirmResult"](confirmed=allow, tool_call=tc, rules=None))
                break
            else:
                return None  # cancelled：中断整批
        return results

    def _poll_decision(self):
        try:
            return self.decision_queue.get_nowait()
        except queue.Empty:
            return None

    def submit_decision(self, confirm_id: str, allow: bool) -> bool:
        """决策端点投递回执；confirm_id 未注册/已消费 → False（端点转 404）。"""
        if confirm_id not in self.pending:
            return False
        self.touch()  # 采纳/回执也是一种「有人在看」：刷新孤儿回收判据
        self.decision_queue.put({"confirm_id": confirm_id, "allow": allow})
        return True

    def touch(self) -> None:
        """活跃打点：消费端（events/status 轮询/decision 回执）在看本会话，刷新 reaper 判据。"""
        self._last_consumer_seen = time.monotonic()

    @property
    def done_consumed(self) -> bool:
        """SSE 消费端是否已读到终端帧（done/error）。generate 收尾据此决定是否幂等释放槽位。"""
        return self._done_seen

    def is_parked(self) -> bool:
        """是否有待用户回执的确认（worker 正停在 _await_decisions 等人）→ reaper 据此判回收。"""
        return bool(self.pending)

    def current_confirm(self) -> dict | None:
        """当前「待回执确认」摘要（/chat/status 采纳/重显用）；无 → None。
        仅取该批首个：前端逐条回执后重查 status，批内其余确认会依次浮现。"""
        if not self.pending:
            return None
        tc = next(iter(self.pending.values()))
        return {
            "confirm_id": tc.id,
            "name": tc.name,
            "action": (tc.input or "")[:_DETAIL_LIMIT],  # 摘要截断同 confirm_request，不入密钥
            "reason": CONFIRM_REASON,
        }

    # ---- 对外读取（SSE 生成器侧）----
    def events(self):
        """阻塞读 msg_queue 直到收到终端事件（done/error）或会话被取消/断开。

        为什么不能以「worker 线程结束」作为终止判据：worker 在 finally 里 push done/error
        *之后*才退出，二者是 happens-before 关系——若消费方此刻才进入、线程已退出，按线程
        存活判据会提前返回，把尚在队列里的 done 漏掉（快脚本下常见的竞态）。故只认终端帧
        或显式取消/脱离。
        保活：空闲超过 _HEARTBEAT_SECONDS 时发一条 SSE 注释帧 ": ping"，既让代理/浏览器别按
        空闲掐断长连接，也让停留确认时连接保持可写（真正的断开只在「写」时报错被感知）。
        本方法每轮都把 _last_consumer_seen 刷到当前——前台连着读即视为有人在看，reaper 不回收。
        """
        last_sent = time.monotonic()
        while not self._cancelled.is_set():
            self._last_consumer_seen = time.monotonic()
            try:
                frame = self.msg_queue.get(timeout=0.5)
            except queue.Empty:
                if time.monotonic() - last_sent >= _HEARTBEAT_SECONDS:
                    last_sent = time.monotonic()
                    yield ": ping\n\n"
                continue
            last_sent = time.monotonic()
            yield frame
            if frame.startswith("data: ") and json.loads(frame[6:-2]).get("type") in ("done", "error"):
                # 以终端帧自然结束：打标记，generate 收尾据此幂等释放注册表槽位（详见 dispose/worker finally）
                self._done_seen = True
                return

    def _push(self, data: dict) -> None:
        self.msg_queue.put(_sse(**data))

    # ---- 取消与释放 ----
    def cancel(self) -> None:
        """连接断开/主动取消：标记取消并唤醒 worker 决策等待/流式循环。"""
        self._cancelled.set()
        self.decision_queue.put({"confirm_id": "__cancel__", "allow": False})

    def dispose(self) -> None:
        """join worker 线程（可重复调用）。MCP 已在 worker finally 关闭。

        cancel+dispose 是「停止 run」专用路径（POST /chat/stop）：worker 被唤醒后自注销；
        若 join 超时（模型长调用未及时归位），调用方仍需显式 unregister 兜底释放槽位。
        普通 SSE 断开不调本方法——那是「脱离」，run 继续后台跑并由 worker 自注销收尾。"""
        self.cancel()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=8)


# ============================================================
# 每任务单活动会话注册表（spec R2：并发 chat → 409）
# ============================================================
_sessions: dict = {}
_registry_lock = threading.Lock()


def active_session(task_id: int) -> "ChatSession | None":
    return _sessions.get(task_id)


def register(task_id: int, sess: "ChatSession") -> bool:
    """登记会话；已有活动会话 → False（端点据此 409）。首个成功登记时懒启动孤儿回收守护。"""
    with _registry_lock:
        if task_id in _sessions:
            return False
        _sessions[task_id] = sess
        _ensure_reaper()
        return True


def unregister(task_id: int) -> None:
    _sessions.pop(task_id, None)


# 孤儿 park 会话回收守护（保活设计的配套防泄漏）：
# 保活改造后 SSE 断开不再取消 run；若 run 停在一个「无人认领」的确认上且用户不再回来，
#   活动槽会被永久占用（再次 chat → 永久 409，即最初卡死问题）。本守护定时扫描：凡「停在待
#   回执确认」且消费端 beat（_last_consumer_seen）超过 _CONSUMER_TTL 未刷新 → cancel 唤醒 worker
#   → worker finally 自注销，槽位自动释放。只回收 park 的会话；正常后台 run 跑完即自注销，不受影响。
_reap_started = False
_reap_lock = threading.Lock()


def _ensure_reaper() -> None:
    """进程内单例：首个成功 register 时懒启动回收线程（纯单元场景不打扰）。"""
    global _reap_started
    with _reap_lock:
        if _reap_started:
            return
        _reap_started = True
    threading.Thread(target=_reap_loop, name="ls-session-reaper", daemon=True).start()


def _reap_loop() -> None:
    while True:
        time.sleep(_REAP_INTERVAL)
        _reap_once()


def _reap_once() -> None:
    """扫一遍注册表：回收「停驻待确认且消费端长期无 beat」的孤儿会话。单测可直接调用。

    被回收 = cancel 该会话 → worker 的决策等待被唤醒返回 None → worker finally 自注销，
    槽位自动释放（端点无需干预）。单次扫描绝不因个别异常中断其余项。"""
    try:
        with _registry_lock:
            snapshot = list(_sessions.values())
        now = time.monotonic()
        for sess in snapshot:
            if sess.is_parked() and (now - sess._last_consumer_seen) > _CONSUMER_TTL:
                sess.cancel()
    except Exception:  # noqa: BLE001 —— 单次扫描绝不因异常退出
        pass
