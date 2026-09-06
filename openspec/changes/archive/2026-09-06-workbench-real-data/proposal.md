## Why

`workbench-ui` 主 spec 定稿于 P4~P6 后端交付之前，其中 R6（可折叠细节栏）与 R9（设置中心/注册中心抽屉）仍把「技能 / 资料 / MCP」分区与注册中心四入口写成**未交付→稳定空态占位**。P4（capability-mount）、P5（registry-center）、P6（library）已交付并被前端实数据化（挂载编辑、CRUD 面板、库引用文件树），但 spec 文字仍停留在占位态，会让验收方按字面把“有实数据”误判为偏差。需把这两条需求的条件句更新到“已交付→实数据；未交付远期区→稳定空态”。

## What Changes

- 修改 `workbench-ui` capability 的两条需求（纯 spec 文字，无行为新增，无代码改动）：
  - R6「可折叠细节栏与任务模型绑定」：技能/资料/MCP 分区由“空态占位”改为“已交付时展示任务真实挂载/库引用并支持编辑；未交付（远期权限模板）仍稳定空态”。
  - R9「设置中心与注册中心抽屉、暗色模式」：注册中心四类入口由“空态占位”改为“已交付时承载真实 CRUD 管理；不存在可管理项时为空态说明”。
- 同步更新对应 Scenario 的可观察结果描述（含 权限模板/自动化 远期占位措辞）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench-ui`: R6 细节栏分区与 R9 注册中心由“未交付空态”更新为“交付后实数据 + 远期区占位”的条件语义。

## Impact

- 仅影响 `openspec/specs/workbench-ui/spec.md` 主 spec 的两段需求文字与场景描述。
- 不触碰任何代码 / API / 依赖；前端实数据能力已于前序会话交付在树中。
- 归档时经 delta sync 合并回主 spec，不改动已归档其余 capability。
