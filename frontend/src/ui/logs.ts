import type { LogEntry } from '../types';
import { getState, setState } from '../state/store';
import { $, el } from '../utils/dom';
import { escapeHtml, formatLlmUsage, getToolConfig } from '../utils/formatters';
import { renderMarkdown } from '../utils/markdown';

function getLogKey(entry: LogEntry): string {
  const step = entry.step ?? '';
  return `${entry.role}|${step}|${entry.content.slice(0, 200)}`;
}

function renderToolCall(toolName: string, args: Record<string, unknown>): string {
  const cfg = getToolConfig(toolName);
  const argsHtml = escapeHtml(JSON.stringify(args, null, 2));

  return `
    <div class="log-tool-call log-tool-${escapeHtml(toolName)}">
      <div class="log-tool-title">
        <i class="${cfg.icon}" style="color:${cfg.color}"></i>
        Tool Action: ${escapeHtml(toolName)}
      </div>
      <div class="log-tool-args">
        <div class="log-collapsible-text">${argsHtml}</div>
      </div>
    </div>
  `;
}

function renderAssistantContent(content: string): string {
  const jsonMatch = content.match(/\{[^{}]*"tool"\s*:/);
  if (jsonMatch) {
    const startIdx = jsonMatch.index!;
    let braceCount = 0;
    let inString = false;
    let escapeNext = false;
    let endIdx = startIdx;

    for (let i = startIdx; i < content.length; i++) {
      const char = content[i];
      if (escapeNext) { escapeNext = false; continue; }
      if (char === '\\') { escapeNext = true; continue; }
      if (char === '"') { inString = !inString; continue; }
      if (inString) continue;
      if (char === '{') braceCount++;
      else if (char === '}') {
        braceCount--;
        if (braceCount === 0) { endIdx = i + 1; break; }
      }
    }

    if (braceCount === 0) {
      try {
        let jsonStr = content.substring(startIdx, endIdx);
        jsonStr = jsonStr
          .replace(/(?<="[^"]*)\n(?=[^"]*")/g, '\\n')
          .replace(/(?<="[^"]*)\r(?=[^"]*")/g, '\\r')
          .replace(/(?<="[^"]*)\t(?=[^"]*")/g, '\\t');
        const data = JSON.parse(jsonStr);
        return renderToolCall(data.tool, data.args ?? {});
      } catch {
        // fall through
      }
    }
  }

  return `<div class="log-markdown">${renderMarkdown(content)}</div>`;
}

function renderEntryBody(entry: LogEntry): string {
  if (entry.role === 'assistant') {
    return renderAssistantContent(entry.content);
  }

  if (entry.role === 'tool_result') {
    return `<div class="log-plain log-tool-result-text"><div class="log-collapsible-text">${escapeHtml(entry.content)}</div></div>`;
  }

  return `<div class="log-markdown">${renderMarkdown(entry.content)}</div>`;
}

function renderCollapsibleCard(bodyHtml: string, rawContent: string, entryKey: string): string {
  if (rawContent.length <= 300) return bodyHtml;

  const isExpanded = getState('expandedLogs').has(entryKey);
  const previewText = rawContent.slice(0, 300);
  const preview = `${renderMarkdown(previewText)}<span class="log-collipsis">...</span>`;

  return `
    <div class="log-collapsible-card">
      <div class="log-collapsible-preview" style="display: ${isExpanded ? 'none' : 'block'};">
        ${preview}
      </div>
      <button type="button" class="log-expand-btn" data-expanded="${isExpanded}" data-entry-key="${encodeURIComponent(entryKey)}">
        ${isExpanded ? 'Recolher' : 'Expandir'}
      </button>
      <div class="log-collapsible-full" style="display: ${isExpanded ? 'block' : 'none'};">
        ${bodyHtml}
      </div>
    </div>
  `;
}

function getRoleIcon(role: string): string {
  const icons: Record<string, string> = {
    system: '<i class="fa-solid fa-server"></i>',
    assistant: '<i class="fa-solid fa-robot"></i>',
    tool_result: '<i class="fa-solid fa-terminal"></i>',
    user_intervention: '<i class="fa-solid fa-user-pen"></i>',
    supervisor: '<i class="fa-solid fa-shield-halved"></i>',
  };
  return icons[role] ?? icons.system;
}

function renderCard(entry: LogEntry): HTMLElement {
  const card = el('div', { className: `log-card log-role-${entry.role}` });

  const step = entry.step ?? '-';
  let titleText = entry.role.replace(/_/g, ' ').toUpperCase();

  if (entry.role === 'supervisor' && entry.content.includes('🛡️ Supervisor agindo após erro')) {
    titleText = '<span style="color: #cf222e;">🛡️ SUPERVISOR AGINDO APÓS ERRO</span>';
  }

  const usageBadge = entry.llm_usage
    ? `<span class="log-usage-badge">${escapeHtml(formatLlmUsage(entry.llm_usage))}</span>`
    : '';

  const bodyHtml = renderEntryBody(entry);
  const entryKey = getLogKey(entry);
  const collapsibleHtml = renderCollapsibleCard(bodyHtml, entry.content, entryKey);

  card.innerHTML = `
    <div class="log-card-header">
      <span>${getRoleIcon(entry.role)} ${titleText} (Step ${step})</span>
      ${usageBadge}
    </div>
    <div class="log-card-body">${collapsibleHtml}</div>
  `;

  return card;
}

export function renderLogs(logs: LogEntry[]): void {
  const container = $('#execution-log') as HTMLElement | null;
  if (!container) return;

  const currentId = getState('currentTaskId');
  if (container.dataset.taskId !== currentId) {
    container.dataset.taskId = currentId ?? '';
  }

  const preserveScroll = container.scrollTop;
  container.innerHTML = '';
  setState('renderedLogs', new Set());
  const rendered = getState('renderedLogs');

  for (const entry of logs) {
    const key = getLogKey(entry);
    rendered.add(key);
    container.appendChild(renderCard(entry));
  }

  if (getState('logAutoScroll')) {
    container.scrollTop = container.scrollHeight;
  } else {
    container.scrollTop = preserveScroll;
  }
}

export function initLogScroll(): void {
  const container = $('#execution-log') as HTMLElement | null;
  if (!container) return;

  container.addEventListener('scroll', () => {
    const threshold = 20;
    const atBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
    setState('logAutoScroll', atBottom);
  });

  container.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const btn = target.closest('.log-expand-btn') as HTMLElement | null;
    if (!btn) return;

    const entryKey = decodeURIComponent(btn.dataset.entryKey ?? '');
    const expanded = btn.dataset.expanded === 'true';
    const card = btn.closest('.log-collapsible-card');
    if (!card) return;

    const preview = card.querySelector<HTMLElement>('.log-collapsible-preview');
    const full = card.querySelector<HTMLElement>('.log-collapsible-full');

    if (expanded) {
      if (preview) preview.style.display = 'block';
      if (full) full.style.display = 'none';
      btn.textContent = 'Expandir';
      btn.dataset.expanded = 'false';
      getState('expandedLogs').delete(entryKey);
    } else {
      if (preview) preview.style.display = 'none';
      if (full) full.style.display = 'block';
      btn.textContent = 'Recolher';
      btn.dataset.expanded = 'true';
      getState('expandedLogs').add(entryKey);
    }
  });
}
