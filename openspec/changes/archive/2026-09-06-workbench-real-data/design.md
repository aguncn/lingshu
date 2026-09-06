## Context

`workbench-ui` 主 spec 的 R6（细节栏分区）与 R9（注册中心）写成 P4~P6 交付前的“空态占位”。P4/P5/P6 后端已交付且前端实数据化完成（挂载编辑、注册中心 CRUD、资料引用/预览分流），本 change 只把这两段 spec 文字同步到“已交付→实数据；远期区→稳定占位”。

## Goals / Non-Goals

**Goals:**
- 让 R6/R9 的需求与场景可观察地反映当前系统行为，消除“有实数据却按占位字面验收”的误判。

**Non-Goals:**
- 不做任何代码/API/行为改动；不新增或删除分区与注册中心入口。
- 不改动其余 capability 的主 spec。

## Decisions

- **无架构决策**：本 change 不触碰实现，只更新 spec 契约文字。delta 采用整段 `MODIFIED Requirements`（含完整场景）以便归档 sync 精确合入主 spec。
- 远期占位仍保留：权限模板分区、自动化导航明确不在此 change 内启用。

## Risks

- 最低：唯一风险是 delta 与主 spec 目标需求名不一致导致 sync 失配——通过保留原需求名 `可折叠细节栏与任务模型绑定` / `设置中心与注册中心抽屉、暗色模式` 规避，归档时按名合并即可。
