## ADDED Requirements

### Requirement: 内置工具调用权限档位映射

系统 SHALL 在组装对话 Agent 时按任务的 `permission_mode` 把内置工具调用的二次确认档位映射进 AgentScope 权限上下文：`strict` → 默认模式——内置写/执行类工具（Bash/Read/Write/Edit/Glob/Grep/PowerShell）被请求即产 `confirm_request`，用户放行才执行（与旧行为逐字一致）；`trusted` → 完全信任——全程不请求人工确认、工具直接执行；`limited` → 有限——只读与一般命令自动放行，仅「修改/新建本地文件的 Write/Edit」及「命令中出现删除/覆盖类操作」请求一次确认。未知/缺失取值 SHALL 兜底最严的 `strict`。

`limited`/`trusted` 的映射 SHALL 采用「`BYPASS` 默认全放 + 少量 ask 规则命中才确认」的负向枚举（无法正向穷举安全命令），并因此以「信任模型行为」为前提：`BYPASS` SHALL 跳过工具自带的 bypass-immune 引擎级安全确认（如 `rm -rf /` 之类保护），相关兜底由系统提示约束承担。删除/覆盖类判定对 Bash SHALL 用命令子串规则（`rm`/`rmdir`/`unlink`/`shred`/`mv`/`cp`/`sed -i` 等）；对 PowerShell SHALL 以命令内容做**大小写不敏感**的子串匹配（覆盖 `remove-item`/`del`/`erase`/`move-item`/`copy-item`/`set-content`/`out-file` 等；等价别名与内联改写属启发式边界——命中则多确认一次（安全向）、漏判则少确认一次，不作精确分类承诺）。工具自身 `DENY` 规则与用户 ask/deny 规则 SHALL 仍保留生效。

权限模式 SHALL 在每次会话发起时按任务当前值即时取用（装配即快照）：运行中改动任务 `permission_mode` 不影响正在运行的 run，只作用于之后新发起的 run。

#### Scenario: strict 与旧行为逐字一致

- **WHEN** 任务 `permission_mode` 为 `strict`（或缺省）发起含写/执行类工具的对话
- **THEN** 与默认模式一致：写/执行类工具被请求即出现 `confirm_request`，放行后执行并流出 `tool_result`、拒绝则不执行；审计均记录

#### Scenario: trusted 全程免人工确认

- **WHEN** 任务 `permission_mode` 为 `trusted` 发起含写/执行类工具的对话
- **THEN** 工具调用不出现 `confirm_request`、直接执行并流出 `tool_result`；审计记录工具执行

#### Scenario: limited 仅对危险子集确认

- **WHEN** 任务 `permission_mode` 为 `limited` 发起对话，模型依次执行只读命令（如 Grep）、`Bash "rm -rf /tmp/x"` 删除命令与一次 Write 写文件
- **THEN** 只读与一般命令自动放行无确认；`rm`（命中删除子串）与 Write 各出现一次 `confirm_request`，放行后才执行；PowerShell `Remove-Item` 同样命中（大小写不敏感）

#### Scenario: 运行中改档只影响后续 run

- **WHEN** 用户在任务运行中 `PATCH` 其 `permission_mode`（如 `strict`→`trusted`），随后再发一条新消息
- **THEN** 正在运行的 run 按原档不受影响；新发起的 run 按新档装配（装配描述中 `permission_mode` 反映新值，无确认请求）
