#!/usr/bin/env python3
"""极简 MCP stdio JSON-RPC 服务端（测试替身，P5 registry-center design D6）。

真实 MCP server（如 npx mcp-server-sqlite）依赖外部运行时、无法在 CI 稳定复现，
故连通性测试的「成功」路径由本脚本驱动：command=sys.executable、args=[本文件路径]。
协议：换行分隔 JSON-RPC（MCP stdio transport）；逐行处理 stdin，响应写 stdout 并 flush。
仅回应三件事：initialize(id) → 握手成功；notifications/initialized → 静默；tools/list(id) → 固定 2 个工具。
"""
import json
import sys

_TOOLS = [
    {
        "name": "fake_metrics_query",
        "description": "示例工具：查询指标（连通测试用，无真实后端）",
        "inputSchema": {"type": "object", "properties": {"metric": {"type": "string"}}},
    },
    {
        "name": "fake_log_tail",
        "description": "示例工具：拉取日志尾部（连通测试用，无真实后端）",
        "inputSchema": {"type": "object"},
    },
]


def _send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "lingshu-fake-server", "version": "0.1.0"},
                },
            })
        elif method == "notifications/initialized":
            pass  # 通知类无响应
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": _TOOLS}})


if __name__ == "__main__":
    main()
