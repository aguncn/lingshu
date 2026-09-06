# OpenSpec Project — 灵枢 (Lingshu)

## 项目简述
灵枢是一个**面向 IT 运维领域**的智能体平台（非通用平台）。以「任务」为最小运行单元，将大模型 + 技能 + MCP + 知识库 + 专家装配为可复用的运维智能体。核心差异点是 12 大运维场景域，每域有独立提示词模板与差异化上下文注入/能力装配。

## 技术栈
- 后端：Python 3.12 + Flask + Flask-CORS + SQLAlchemy + SQLite（uv 管理）
- 前端：Vue 3 + Vite + Element Plus + Pinia + Axios
- 智能体运行时：AgentScope >= 2.06（ReAct + MCP + 流式事件 + Permission）
- 规范驱动：OpenSpec SDD（Claude Code + ccswitch → DeepSeek V4 Flash）

## 设计权威参考
- `灵枢_技术方案与架构设计.md`：架构、数据模型、接口契约、AgentScope 集成
- `灵枢_开发计划与OpenSpec提案任务书.md`：10 个 P0 提案、每提案 ~10 任务、验收命令
- `灵枢_开发执行手册.md`：环境、CLAUDE.md、命令流、apply/verify/archive

## 本期范围（P0）
空间与任务管理(TR)、模型与提示词(MD)、能力装配(CAP)、注册中心(AD)、资料库(LB)、
三栏工作台 UI(UI-01~07)、AgentScope 运行时、十二域场景模板(§8/§9)、安全与审计(NF)。

## 后续范围（P1/P2）
自动化(AU)、深度 MCP 真实连接器、多专家协作编排、变更/告警/故障深度编排、
容量预测、运维知识图谱、向量化 RAG。

## 约定
- 每个变更 = 一个能力域；tasks.md 每条可独立验收（8–12 条）。
- 数据库变更走 `backend/migrations/NNNN_*.sql` + 轻量迁移器，不用 Alembic。
- 密钥加密存储，展示脱敏；内置写类工具默认 confirm（二次确认）。
