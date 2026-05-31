import { marked } from 'marked';

marked.setOptions({
  breaks: false,
  gfm: true,
  async: false,
});

export function renderMarkdown(text: string): string {
  const result = marked.parse(text, { async: false });
  if (typeof result === 'string') return result;
  return text;
}
