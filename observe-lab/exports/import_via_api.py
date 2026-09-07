"""一键把 observe-lab 的接入物导入灵枢 backend（可选通道；主通道是 UI，见 import-checklist.md）。

作用：按 exports/lingshu-*.json + lingshu-skills|kb|library 里的文件，在灵枢 REST 上自动创建：
  技能(5) → MCP 连接器(openobserve-ec，http 原生 O2) → 知识库(observe-lab-sre-kb + runbook 文档)
  → 资料库(3 份速查) → 专家「SRE 值班专家·observe-lab」（预设全部接线）。
之后可任选一步：把专家应用到某个任务（--task-title）→ 灵枢模型就能带着 O2 MCP + runbook 做诊断。

灵枢接口事实（写脚本时对 backend 核实过，2026-09）：
- 全部走 /api、**无鉴权**、JSON 请求需 Content-Type: application/json（requests 传 json= 自动带）。
- name 全局唯一，重名返回 400 {"message":"name 已存在：…"} → 一律视作“已存在”按名复用，不报错。
- 错误统一 {"message": "<中文>"}，400 校验/404 未找到。
- 创建多数返回 201 + 完整对象；知识库/资料上传=multipart；KB 一个文件一次 upload。
用法：
  uv run python exports/import_via_api.py [--base http://localhost:5000/api] [--task-title "电商异常诊断演示"]
  uv run python exports/import_via_api.py --dry-run     # 只打印将要做什么
环境：OO_BASE_URL/OO_ORG/OO_EMAIL/OO_PASSWORD 可来自 observe-lab/.env（脚本自动读）或环境变量。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent          # observe-lab/
EXPORTS = ROOT / "exports"
SKILLS_DIR = EXPORTS / "lingshu-skills"
KB_DIR = EXPORTS / "lingshu-kb"
LIB_DIR = EXPORTS / "lingshu-library"
MCP_JSON = EXPORTS / "lingshu-mcp.json"
EXPERT_JSON = EXPORTS / "lingshu-expert-sre.json"

KB_NAME = "observe-lab-sre-kb"   # 与 expert json presets.kbs 一致


# ---------- .env / 环境读取 ----------
def load_dotenv() -> None:
    """极简 .env 解析：把文件里的 KEY=VALUE 塞进环境变量（不覆盖已存在的）。"""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default) or default


# ---------- API 薄封装 ----------
class Ling:
    def __init__(self, base: str, dry: bool = False):
        self.base = base.rstrip("/")
        self.dry = dry
        self.created: list[str] = []
        self.reused: list[str] = []

    def _req(self, method, path, **kw):
        url = f"{self.base}/{path.lstrip('/')}"
        if self.dry:
            return {"_dry": True, "method": method, "url": url, **kw}
        r = requests.request(method, url, timeout=30, **kw)
        if r.status_code >= 400:
            msg = (r.json() or {}).get("message", r.text[:200]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
            raise ApiError(r.status_code, path, msg)
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else {}

    def get_list(self, path: str):
        if self.dry:
            return []
        return self._req("GET", path)

    def post_json(self, path: str, body: dict):
        if self.dry:
            print(f"  [dry] POST {path} {json.dumps(body, ensure_ascii=False)[:160]}")
            return None
        return self._req("POST", path, json=body)

    def patch_json(self, path: str, body: dict):
        if self.dry:
            print(f"  [dry] PATCH {path} {json.dumps(body, ensure_ascii=False)[:160]}")
            return None
        return self._req("PATCH", path, json=body)

    def post_files(self, path: str, filename: str, data: bytes):
        if self.dry:
            print(f"  [dry] POST {path} (multipart file={filename})")
            return None
        return self._req("POST", path, files={"file": (filename, data, "text/markdown")})

    def existing_id(self, path: str, name: str) -> int | None:
        if self.dry:
            return None
        for it in self._req("GET", path):
            if it.get("name") == name:
                return it["id"]
        return None


class ApiError(Exception):
    pass


def find_by_name(items, name):
    for it in items:
        if it.get("name") == name:
            return it
    return None


def is_dup(e: ApiError) -> bool:
    return e.status == 400 and "已存在" in e.message


# ---------- 各步 ----------
def ensure_skill(ling: Ling) -> list[int]:
    print("\n== 技能 ==")
    ids: list[int] = []
    for p in sorted(SKILLS_DIR.glob("*.md")):
        name = p.stem
        md = p.read_text(encoding="utf-8")
        desc = next((ln.lstrip("# ").strip() for ln in md.splitlines() if ln.strip() and not ln.startswith("#!")), "")
        ex = ling.existing_id("skills", name)
        if ex is not None:
            print(f"  • 技能 {name} 已存在(id={ex})，复用")
            ling.reused.append(f"skill:{name}")
            ids.append(ex)
            continue
        try:
            obj = ling.post_json("skills", {"name": name, "description": desc, "skill_md": md, "enabled": True})
            if obj:
                print(f"  ✓ 技能 {name} 建好(id={obj['id']})")
                ling.created.append(f"skill:{name}")
                ids.append(obj["id"])
        except ApiError as e:
            if is_dup(e):
                ids.append(ling.existing_id("skills", name))
                print(f"  • 技能 {name} 撞名(400 已存在)，已按名复用")
            else:
                raise
    return ids


def ensure_mcp(ling: Ling) -> list[int]:
    print("\n== MCP 连接器 ==")
    ids: list[int] = []
    cfg = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    for c in cfg["connectors"]:
        if not c.get("enabled"):
            print(f"  - 跳过(disabled): {c['payload']['name']}")
            continue
        payload = dict(c["payload"])
        if payload["transport"] == "http":
            basic = base64.b64encode(f"{env('OO_EMAIL')}:{env('OO_PASSWORD')}".encode()).decode()
            payload["headers"] = {"Authorization": f"Basic {basic}"}
        else:  # stdio：env 占位符换成实际值
            payload["env"] = {
                k: (env(v.strip("<>")) if v.startswith("<") and v.endswith(">") else v)
                for k, v in payload["env"].items()
            }
        ex = ling.existing_id("mcp", payload["name"])
        if ex is not None:
            print(f"  • MCP {payload['name']} 已存在(id={ex})，复用")
            ling.reused.append(f"mcp:{payload['name']}")
            ids.append(ex)
            # 已存在也要把 enabled/trust 对齐到模板（幂等修形；PATCH 部分更新）
            ling.patch_json(f"mcp/{ex}", {k: payload[k] for k in ("enabled", "trust") if k in payload})
            continue
        obj = ling.post_json("mcp", payload)
        if not obj:
            continue
        print(f"  ✓ MCP {payload['name']} 建好(id={obj['id']})")
        ling.created.append(f"mcp:{payload['name']}")
        ids.append(obj["id"])
        # 测试连接器（http 原生 O2；失败多为凭据/org，业务返回 ok:false 不算异常）
        if not ling.dry:
            try:
                t = ling._req("POST", f"mcp/{obj['id']}/test")
                ok = t.get("ok")
                print(f"    ↳ 测试: ok={ok} tools={t.get('tool_count')} {('原因:'+str(t.get('reason'))) if not ok else ''}")
            except ApiError as e:
                print(f"    ↳ 测试失败(HTTP {e.status}): {e.message} —— 核对 OO_* 与 O2 是否在跑")
    return ids


def ensure_kb(ling: Ling) -> int:
    print("\n== 知识库(RAG) ==")
    ex = ling.existing_id("kb", KB_NAME)
    if ex is not None:
        kid = ex
        print(f"  • KB {KB_NAME} 已存在(id={kid})，复用；将重灌文档（同名文件覆盖）")
    else:
        obj = ling.post_json("kb", {"name": KB_NAME, "status": "ready", "chunk_size": 400})
        if not obj:
            return 0
        kid = obj["id"]
        print(f"  ✓ KB {KB_NAME} 建好(id={kid})")
        ling.created.append(f"kb:{KB_NAME}")
    if ling.dry:
        return kid
    for p in sorted(KB_DIR.glob("*.md")):
        r = ling.post_files(f"kb/{kid}/upload", p.name, p.read_bytes())
        print(f"  ✓ 上传 {p.name} → {r.get('chunk_count')} chunks")
    return kid


def ensure_library(ling: Ling) -> list[int]:
    print("\n== 资料库 ==")
    ids: list[int] = []
    if ling.dry:
        return ids
    existing = {it["filename"]: it["id"] for it in ling._req("GET", "library?scope=all")}
    for p in sorted(LIB_DIR.glob("*.md")):
        if p.name in existing:
            print(f"  • 资料 {p.name} 已存在(id={existing[p.name]})，复用（同名文件不重复上传；想换内容先删旧的再跑）")
            ids.append(existing[p.name])
            ling.reused.append(f"lib:{p.name}")
            continue
        obj = ling.post_files("library", p.name, p.read_bytes())
        print(f"  ✓ 资料 {p.name} 建好(id={obj['id']})")
        ling.created.append(f"lib:{p.name}")
        ids.append(obj["id"])
    return ids


def ensure_expert(ling: Ling, mcp_ids: list[int], kid: int) -> int | None:
    print("\n== 专家 ==")
    cfg = json.loads(EXPERT_JSON.read_text(encoding="utf-8"))["expert"]
    presets = cfg["presets"]
    name = cfg["name"]
    ex = ling.existing_id("experts", name)
    if ex is not None:
        print(f"  • 专家 {name} 已存在(id={ex})，复用（不覆盖，避免误改你手动调过的档案）")
        ling.reused.append(f"expert:{name}")
        return ex

    # 需要按名解析 id：技能/资料名在库里查；KB/MCP 上一步已有 id。
    if not ling.dry:
        skill_by_name = {it["name"]: it["id"] for it in ling._req("GET", "skills")}
        lib_by_name = {it["filename"]: it["id"] for it in ling._req("GET", "library?scope=all")}
    else:
        skill_by_name = lib_by_name = {}
    body = {
        "name": name,
        "description": cfg["description"],
        "system_prompt": cfg["system_prompt"],
        "role": cfg["role"],
        "enabled": cfg["enabled"],
        "preset_skills": [skill_by_name[n] for n in presets["skills"] if n in skill_by_name],
        "preset_mcp": mcp_ids,
        "preset_kb": [kid] if kid else [],
        "preset_library": [lib_by_name[n] for n in presets["library"] if n in lib_by_name],
    }
    if not body["preset_skills"] or not body["preset_mcp"] or not body["preset_kb"]:
        print("  ! 预设解析为空（技能/MCP/KB 前置步骤可能没建成功），仍创建专家但预设可能不全；请查上方输出。")
    try:
        obj = ling.post_json("experts", body)
        if not obj:
            return None
        print(f"  ✓ 专家 {name} 建好(id={obj['id']})")
        ling.created.append(f"expert:{name}")
        return obj["id"]
    except ApiError as e:
        if is_dup(e):
            return ling.existing_id("experts", name)
        raise


def apply_to_task(ling: Ling, eid: int, title: str):
    print("\n== 建任务 + 应用专家 ==")
    if ling.dry:
        print(f"  [dry] 将创建任务『{title}』并 POST /tasks/<tid>/expert/apply {{expert_id:{eid}}}")
        return
    spaces = ling._req("GET", "spaces")
    sid = spaces[0]["id"] if spaces else ling._req("POST", "spaces", json={"name": "observe-lab 演示", "visibility": "private"})["id"]
    tid = ling._req("POST", f"spaces/{sid}/tasks", json={"title": title, "task_type": "fault", "permission_mode": "strict"})["id"]
    out = ling._req("POST", f"tasks/{tid}/expert/apply", json={"expert_id": eid})
    print(f"  ✓ 任务 id={tid}，已应用专家 → mounted={json.dumps(out.get('mounted'), ensure_ascii=False)}")
    print(f"  → 下一步：打开灵枢，在该任务里发问（见 docs/06）。")


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="observe-lab → 灵枢 一键导入")
    ap.add_argument("--base", default=env("LINGSHU_API", "http://localhost:5000/api"))
    ap.add_argument("--task-title", default="电商下单异常诊断演示（observe-lab）")
    ap.add_argument("--no-task", action="store_true", help="只导资产，不建任务/不应用专家")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not (env("OO_EMAIL") and env("OO_PASSWORD")):
        print("需要 OO_EMAIL/OO_PASSWORD（observe-lab/.env 或环境变量）来拼 O2 MCP 的 Basic 头。先看 docs/01。")
        sys.exit(2)

    ling = Ling(a.base, dry=a.dry_run)
    print(f"目标灵枢 API: {a.base}" + ("  [DRY-RUN 只打印不落库]" if a.dry_run else ""))

    ensure_skill(ling)
    mcp_ids = ensure_mcp(ling)
    kid = ensure_kb(ling)
    ensure_library(ling)
    eid = ensure_expert(ling, mcp_ids, kid)
    if eid and not a.no_task and not a.dry_run:
        apply_to_task(ling, eid, a.task_title)

    print("\n" + "=" * 56)
    print(f"新建 {len(ling.created)} · 复用 {len(ling.reused)}")
    for c in ling.created:
        print("  +", c)
    if a.no_task:
        print("\n（未建任务/应用专家。之后可在 UI 建任务 → 挂该专家，见 import-checklist.md / docs/05。）")


if __name__ == "__main__":
    main()
