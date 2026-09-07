## Why

P8 会话助手回复正文目前把模型输出的 Markdown **原样当文本**展示：`##`、`**`、列表、代码块等格式化符号全部字面可见，观感接近纯文本——字号小、无层级、无配色，多步骤长回复尤其难读。浏览器里实际就是要「把 md 渲染成 md 文件预览后的样子：更大、有颜色、有标题、有缩进、更漂亮」。浏览器手工验收通过，现回填规范并归档。

## What Changes

- **新增渲染工具** `frontend/src/utils/md.js`：封装 `markdown-it`（v14）——`html:false` 把模型输出中的原始 HTML 一律按文本转义（不执行、不注入，XSS 安全，无需额外 DOMPurify）；`linkify:true` 把裸 URL 自动识别为可点击链接；`breaks:true` 保留模型单换行结构（chat 里模型常用单换行分步、未必空行）。
- **会话区接入** `components/layout/ChatPane.vue`：助手回复正文由纯文本改为经 `renderMd` 渲染的富文本（`v-html`），用户气泡与错误气泡保持纯文本原样；助手正文为空/进行态时的行为不变。
- **富文本排版**（scoped `:deep` + CSS 令牌）：正文 13px 更大字号；`h1`–`h6` 分级着色（主题高亮 + 下分隔线）；`strong`/`em`/`del` 生效；有序/无序列表与嵌套缩进；行内代码与代码块等宽底色区分；引用（高亮竖条）、表格（描边对齐、表头轻染）、分隔线、图片、链接都有排版；明/暗两套主题配色一致。
- 依赖：`package.json` 新增 `markdown-it@^14`；无后端改动。

## Capabilities

### New Capabilities
<!-- 无新增能力。 -->

### Modified Capabilities
- `workbench-ui`: 会话区助手回复从「Markdown 原样文本」改为「Markdown 富文本渲染」的显示语义。

## Impact

- 前端：`utils/md.js`（新增）、`components/layout/ChatPane.vue`（气泡正文 v-html + md-body 排版样式）、`package.json`（markdown-it）。
- 后端/数据：无改动、无迁移。
- 验证：`npm run build` 通过；手工核验标题/加粗/列表/代码/表格/引用/裸链/换行与 `<script>` 转义。
