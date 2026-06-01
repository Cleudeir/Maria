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
      let jsonStr = content.substring(startIdx, endIdx);
      try {
        const data = JSON.parse(jsonStr);
        return renderToolCall(data.tool, data.args ?? {});
      } catch {
        try {
          jsonStr = jsonStr
            .replace(/\n/g, '\\n')
            .replace(/\r/g, '\\r')
            .replace(/\t/g, '\\t');
          const data = JSON.parse(jsonStr);
          return renderToolCall(data.tool, data.args ?? {});
        } catch {
          // fall through
        }
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

function renderCollapsibleCard(bodyHtml: string): string {
  return bodyHtml;
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
  const collapsibleHtml = renderCollapsibleCard(bodyHtml);

  card.innerHTML = `
    <div class="log-card-header">
      <span>${getRoleIcon(entry.role)} ${titleText} (Step ${step})</span>
      ${usageBadge}
    </div>
    <div class="log-card-body">${collapsibleHtml}</div>
  `;

  return card;
}

function renderCommandOutputCard(output: string): HTMLElement {
  const card = el('div', { className: 'log-card log-role-tool_result log-command-streaming' });

  card.innerHTML = `
    <div class="log-card-header">
      <span><i class="fa-solid fa-terminal"></i> COMMAND OUTPUT (LIVE)</span>
    </div>
    <div class="log-card-body">
      <div class="log-plain log-tool-result-text">
        <div class="log-collapsible-text">${escapeHtml(output)}</div>
      </div>
    </div>
  `;

  return card;
}

export function renderLogs(logs: LogEntry[], commandOutput?: string): void {
  const container = $('#execution-log') as HTMLElement | null;
  if (!container) return;

  const currentId = getState('currentTaskId');
  const taskChanged = container.dataset.taskId !== currentId;
  if (taskChanged) {
    container.dataset.taskId = currentId ?? '';
    container.innerHTML = '';
    setState('renderedLogs', new Set());
  }

  const preserveScroll = container.scrollTop;
  const rendered = getState('renderedLogs');

  for (const entry of logs) {
    const key = getLogKey(entry);
    if (rendered.has(key)) continue;
    rendered.add(key);
    container.appendChild(renderCard(entry));
  }

  const existingCmd = container.querySelector('.log-command-streaming');
  if (commandOutput) {
    if (existingCmd) {
      existingCmd.querySelector('.log-collapsible-text')!.textContent = commandOutput;
    } else {
      container.appendChild(renderCommandOutputCard(commandOutput));
    }
  } else if (existingCmd) {
    existingCmd.remove();
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


}
