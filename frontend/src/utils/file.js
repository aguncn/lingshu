// 文件展示小工具：按 mime/扩展名判断「可预览类别」，字节数友好格式化。
// 用于文件树与预览对话框（design D7：文本/图片预览，其余仅元信息）。

export function formatBytes(bytes) {
  if (bytes == null || Number.isNaN(bytes)) return '—'
  const n = Number(bytes)
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB']
  let v = n / 1024
  let u = units[0]
  for (let i = 0; i < units.length && v >= 1024; i += 1) {
    v /= 1024
    u = units[i + 1] || units[i]
  }
  return `${v.toFixed(1)} ${u}`
}

// 判断展示类别：image → <img>；text → <pre>；binary → 仅元信息
export function fileKind(filename = '', mime = '') {
  if (mime && mime.startsWith('image/')) return 'image'
  const name = (filename || '').toLowerCase()
  const TEXT_EXT = new Set(['.txt', '.md', '.json', '.log', '.csv', '.yml', '.yaml', '.xml', '.js', '.ts', '.py', '.sh', '.sql', '.conf', '.ini', '.html', '.css'])
  if (TEXT_EXT.has(name.slice(name.lastIndexOf('.'))) && !mime.startsWith('image/')) return 'text'
  if (mime && (mime.startsWith('text/') || mime.includes('json') || mime.includes('xml') || mime.includes('yaml') || mime.includes('javascript'))) return 'text'
  return 'binary'
}
