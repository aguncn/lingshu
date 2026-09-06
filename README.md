# 灵枢 (Lingshu) — IT 运维智能体平台

面向 IT 运维领域的智能体平台：以「任务」为最小运行单元，将大模型 + 技能 + MCP + 知识库 + 专家装配为可复用的运维智能体。

> 规范驱动开发：完整方法论见 `docs/灵枢_开发执行手册.md`；架构见 `docs/灵枢_技术方案与架构设计.md`。

## 环境要求

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 20 + npm

## 启动

**后端（Flask，5000 端口）**
```powershell
uv sync
uv run flask --app backend.app run --port 5000
```

**前端（Vue3 + Vite，5173 端口，代理 /api → 5000）**
```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173 ，首页会调用后端健康检查并显示「后端就绪」。

## 冒烟验证

```powershell
curl http://127.0.0.1:5000/api/health
# => {"ok":true,"ts":"..."}
```

## 测试

```powershell
uv run pytest backend/tests/ -q
```

## 目录约定

见 `CLAUDE.md` §2（backend / frontend / openspec）。数据与密钥不入库明文；`.venv`、`backend/data/`、`node_modules`、`.env` 均被 git 忽略。
