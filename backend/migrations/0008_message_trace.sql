-- 0008: 会话过程追溯（session-trace-ui）——messages 增可空 trace 列。
-- 作用：把一次助手回合的有序过程步骤（thinking / tool_call / tool_result / confirm）随该助手消息持久化，
--       使 GET /messages 可回放"这次回答做了什么"，刷新/重开任务仍可追溯。
-- 语义/决策见 session-trace-ui design D1：
--   - trace 是助手消息自身属性（同 model/run_id），随消息行原子写入、读取免 join；
--   - TEXT 存 JSON、nullable：旧行/纯文本回合为 NULL → to_dict 省略该字段，旧客户端向后兼容；
--   - 幂等由 migrate.py 的 schema_version 保证（本脚本只执行一次）。
ALTER TABLE messages ADD COLUMN trace TEXT;
