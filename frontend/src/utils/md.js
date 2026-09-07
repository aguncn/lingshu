// 助手回复 Markdown → HTML 渲染（会话显示美化）。
// 为什么用 markdown-it 而非 marked：默认 html:false 会把模型输出里的原始 HTML 标签按文本转义，
//   无需再串 DOMPurify 就能避免注入——本地模型输出虽相对可信，但「不信任模型可贴任意 HTML」更稳。
// linkify 自动识别裸 URL；breaks:true 保留原文换行（chat 里模型常用单换行切步骤、未必空行），
//   同时 md 结构（标题/加粗/列表/代码）正常排版，观感贴近原文又不失渲染后的富样式。
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false, // 原始 HTML 一律转义为文本（防注入）
  linkify: true, // 裸链接自动成 <a>
  breaks: true, // 保留原文换行（流式逐行上屏/单换行段落都成立）
})

// 空内容不产出 <p></p> 空块（占位气泡 content='' 时走「…」进行态，不经此函数）
export function renderMd(src) {
  if (!src || !src.trim()) return ''
  return md.render(src)
}
