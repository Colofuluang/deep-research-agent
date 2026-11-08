import MarkdownIt from 'markdown-it'

// Reports contain model and webpage text. Keep raw HTML disabled before v-html.
const markdown = new MarkdownIt({ html: false })

markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return renderer.renderToken(tokens, index, options)
}

markdown.renderer.rules.table_open = () => '<div class="report-table"><table>\n'
markdown.renderer.rules.table_close = () => '</table></div>\n'

export function renderMarkdown(text) {
  return markdown.render(text)
}
