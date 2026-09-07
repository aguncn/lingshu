-- 0009: 任务级工具权限模式（task-permission-modes）——tasks 增 permission_mode 列。
-- 作用：把「对话时哪些工具操作需要人工二次确认」提升为任务属性（建任务可选、细节栏可改），
--       使 AgentRuntime 装配时据此选择 PermissionMode 与规则（见 services/agent_runtime.py）。
-- 取值白名单（strict/limited/trusted）在 backend/models.py 顶部 TASK_PERMISSION_MODES 集中维护：
--   strict  严格：全部写/执行类操作二次确认（现状默认，对应 AgentScope PermissionMode.DEFAULT）；
--   limited 有限：只读与一般命令自动放行，仅 Write/Edit 修改与删除类命令仍需确认；
--   trusted 完全信任：全程无需人工确认（BYPASS）。
-- 语义/风险说明见 task-permission-modes design；此处仅加列不迁移既有数据。
-- 幂等由 migrate.py 的 schema_version 保证（本脚本只执行一次）。
ALTER TABLE tasks ADD COLUMN permission_mode TEXT NOT NULL DEFAULT 'strict';
