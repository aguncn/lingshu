## Tasks

> 本 change 为 spec 文字同步：R6/R9 指向的代码能力（挂载编辑、注册中心 CRUD、资料引用/预览分流）已于前序会话交付在树中。apply 阶段无新增代码，逐条确认树内实现与 delta 新文本一致。

- [x] 确认技能/MCP 挂载分区按 R6 新文本经 `GET/PUT /api/tasks/<id>/caps` 展示与全量覆盖编辑（DetailDock 挂载 tile + CapMountDialog），停用/未就绪弱化呈现
- [x] 确认资料分区按 R6 新文本展示 kind=ref 库引用并支持添加/解除引用（解除仅删关联不动库文件），空态与远期权限模板分区为稳定占位
- [x] 确认注册中心按 R9 新文本承载 技能/MCP/知识库/专家 四类 CRUD，MCP 行内连通测试、KB 上传/检索可用，MCP 敏感配置仅展示键名不回显密文
- [x] 回归验证：前端 `npm run build` 通过、后端 `pytest` 通过、活体端点烟测（/skills /mcp /kb /experts /library /tasks/<id>/caps）返回与 UI 期望一致
