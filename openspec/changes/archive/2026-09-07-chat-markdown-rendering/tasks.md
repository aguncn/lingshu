## 1. 渲染工具

- [x] 1.1 `package.json` 新增依赖 `markdown-it@^14`（`npm install markdown-it` 后 lock 一致）
- [x] 1.2 新增 `utils/md.js`：`MarkdownIt({ html:false, linkify:true, breaks:true })` + `renderMd(src)`——`html:false` 转义原始 HTML 防注入、`linkify` 裸链成链接、`breaks` 保留单换行；空内容返回 `''`（不产空 `<p>`）

## 2. 视图接入与富文本排版（components/layout/ChatPane.vue）

- [x] 2.1 助手回复正文气泡改 `v-html="renderMd(m.content)"`（`cp-bubble-text md-body`）；用户气泡与错误气泡保持纯文本原样；助手正文为空且进行中仍走动态「…」占位
- [x] 2.2 scoped 排版：`.md-body` 正文 13px、`line-height:1.75`、`white-space:normal`（v-html 后关掉 pre-wrap）；`:deep` 覆盖 h1–h6 分级大小/主题色/分隔线、strong/em/del、ul/ol 缩进、code/pre 等宽底色、blockquote 高亮竖条、table/th/td 描边对齐表头轻染、hr、img、a（主题色）；首/末元素去外边距；配色走 CSS 令牌明暗自适应

## 3. 验证与收尾

- [x] 3.1 构建通过：`cd frontend && npm run build`
- [x] 3.2 手工核验：`##`/`**`/列表/代码块/表格/引用/裸 URL 渲染为富文本且保留单换行；原始 `<script>` 按可见文本转义不执行；用户气泡与报错气泡仍纯文本
