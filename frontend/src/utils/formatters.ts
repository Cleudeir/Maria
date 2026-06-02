import type { LlmUsage, ToolConfig } from '../types';

const TOOL_CONFIG: Record<string, ToolConfig> = {
  list_dir:          { icon: 'fa-solid fa-folder-open',     color: '#3b82f6' },
  read_file:         { icon: 'fa-solid fa-file-lines',      color: '#06b6d4' },
  write_file:        { icon: 'fa-solid fa-pen-to-square',   color: '#10b981' },
  edit_file:         { icon: 'fa-solid fa-pen',             color: '#f59e0b' },
  edit_lines:        { icon: 'fa-solid fa-lines-leaning',   color: '#f59e0b' },
  grep:              { icon: 'fa-solid fa-magnifying-glass', color: '#a855f7' },
  find_in_files:     { icon: 'fa-solid fa-search',          color: '#a855f7' },
   grep_output:       { icon: 'fa-solid fa-magnifying-glass', color: '#a855f7' },
   run_lint:          { icon: 'fa-solid fa-broom',           color: '#8b5cf6' },
   start_http_server: { icon: 'fa-solid fa-server',          color: '#0ea5e9' },
  stop_http_server:  { icon: 'fa-solid fa-stop',            color: '#f43f5e' },
  list_http_servers: { icon: 'fa-solid fa-list-ul',         color: '#0ea5e9' },
  finish_task:       { icon: 'fa-solid fa-flag-checkered',  color: '#10b981' },
};

export function getToolConfig(name: string): ToolConfig {
  return TOOL_CONFIG[name] ?? { icon: 'fa-solid fa-wrench', color: '#6366f1' };
}

export function escapeHtml(text: string | null | undefined): string {
  if (text == null) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export function formatLlmUsage(usage?: LlmUsage): string {
  if (!usage || typeof usage !== 'object') return '';

  const parts: string[] = [];

  if (Number.isInteger(usage.prompt_tokens)) {
    parts.push(`Prompt: ${usage.prompt_tokens}`);
  }
  if (Number.isInteger(usage.completion_tokens)) {
    parts.push(`Completion: ${usage.completion_tokens}`);
  }
  if (Number.isInteger(usage.total_tokens)) {
    parts.push(`Total: ${usage.total_tokens}`);
  }
  if (Number.isFinite(usage.tokens_per_second)) {
    parts.push(`Speed: ${usage.tokens_per_second} t/s`);
  }
  if (Number.isFinite(usage.prompt_tokens_per_second)) {
    parts.push(`Prompt speed: ${usage.prompt_tokens_per_second} t/s`);
  }
  if (!parts.length && Number.isInteger(usage.tokens)) {
    parts.push(`Total: ${usage.tokens}`);
  }

  return parts.length ? `Ollama:\n${parts.join(' | ')}` : '';
}

export function formatDate(dateStr?: string): string {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return dateStr;
  }
}

export function stripHtmlTags(text: string): string {
  return text.replace(/<[^>]+>/g, '');
}
