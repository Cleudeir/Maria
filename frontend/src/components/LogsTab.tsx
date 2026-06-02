import { useEffect, useRef, useState, useMemo } from 'react';
import type { LogEntry } from '../types';
import { escapeHtml, formatLlmUsage, getToolConfig } from '../utils/formatters';
import { renderMarkdown } from '../utils/markdown';

const COLLAPSE_THRESHOLD = 600;
const SCROLL_THRESHOLD = 100;
const _logsRenderCount = { current: 0 };

type LogFilter = 'all' | 'system' | 'assistant' | 'tool_result' | 'user_intervention' | 'supervisor' | 'errors';

function CollapsibleText({ text, mono }: { text: string; mono?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const shouldCollapse = text.length > COLLAPSE_THRESHOLD;
  const displayText = shouldCollapse && !expanded ? text.slice(0, COLLAPSE_THRESHOLD) + '...' : text;
  return (
    <div>
      <div className={`log-collapsible-text${mono ? ' log-mono' : ''}`}>{escapeHtml(displayText)}</div>
      {shouldCollapse && (
        <button className="log-toggle-btn" onClick={() => setExpanded(!expanded)}>
          <i className={`fa-solid fa-chevron-${expanded ? 'up' : 'down'}`}></i>
          {expanded ? ' Show less' : ` Show all (${text.length.toLocaleString()} chars)`}
        </button>
      )}
    </div>
  );
}

function extractThinkBlocks(content: string): { before: string; think: string; after: string } {
  const thinkStart = content.indexOf('<think>');
  const thinkEnd = content.indexOf('</think>');
  if (thinkStart === -1 || thinkEnd === -1 || thinkEnd <= thinkStart) {
    return { before: content, think: '', after: '' };
  }
  return {
    before: content.slice(0, thinkStart),
    think: content.slice(thinkStart + 7, thinkEnd),
    after: content.slice(thinkEnd + 8),
  };
}

function parseMultipleToolCalls(content: string): Array<{ tool: string; args: Record<string, unknown> }> {
  const calls: Array<{ tool: string; args: Record<string, unknown> }> = [];
  const trimmed = content.trim();

  if (trimmed.startsWith('[')) {
    try {
      const arr = JSON.parse(trimmed);
      if (Array.isArray(arr)) {
        for (const item of arr) {
          if (item && item.tool) {
            calls.push({ tool: item.tool, args: item.args ?? {} });
          }
        }
        if (calls.length > 0) return calls;
      }
    } catch {}
  }

  const re = /\{[^{}]*"tool"\s*:/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(content)) !== null) {
    let braceCount = 0;
    let inString = false;
    let escapeNext = false;
    let endIdx = match.index;
    for (let i = match.index; i < content.length; i++) {
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
        const data = JSON.parse(content.substring(match.index, endIdx));
        if (data.tool) {
          calls.push({ tool: data.tool, args: data.args ?? {} });
        }
      } catch {}
    }
    re.lastIndex = endIdx;
  }
  return calls;
}

function renderToolCall(toolName: string, args: Record<string, unknown>) {
  const cfg = getToolConfig(toolName);
  const argsJson = JSON.stringify(args, null, 2);
  const argSummary = args.path || args.pattern || args.query || Object.keys(args)[0] || '';
  return (
    <div key={`${toolName}-${argSummary}`} className={`log-tool-call log-tool-${escapeHtml(toolName)}`}>
      <div className="log-tool-title">
        <i className={cfg.icon} style={{ color: cfg.color }}></i>
        <span>{escapeHtml(toolName)}</span>
        {argSummary ? <span className="log-tool-arg-summary">{escapeHtml(String(argSummary))}</span> : null}
      </div>
      <div className="log-tool-args">
        {argsJson.length > 300 ? (
          <CollapsibleText text={argsJson} mono />
        ) : (
          <div className="log-collapsible-text log-mono">{escapeHtml(argsJson)}</div>
        )}
      </div>
    </div>
  );
}

function renderToolResult(content: string) {
  const toolResultRegex = /^\[(\w+)\]\s*/gm;
  const segments: Array<{ type: 'tool' | 'text'; label?: string; text: string }> = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(toolResultRegex.source, 'gm');
  while ((m = re.exec(content)) !== null) {
    if (m.index > lastIndex) {
      segments.push({ type: 'text', text: content.slice(lastIndex, m.index) });
    }
    const toolName = m[1];
    const valueStart = m.index + m[0].length;
    const nextMatch = re.exec(content);
    const valueEnd = nextMatch ? nextMatch.index : content.length;
    re.lastIndex = valueEnd;
    segments.push({ type: 'tool', label: toolName, text: content.slice(valueStart, valueEnd) });
    lastIndex = valueEnd;
  }
  if (lastIndex < content.length) {
    segments.push({ type: 'text', text: content.slice(lastIndex) });
  }
  if (segments.length === 0) {
    segments.push({ type: 'text', text: content });
  }

  const isWarning = /WARNING|LOOP DETECTED/i.test(content);
  const isError = /^ERROR/i.test(content);
  let wrapperClass = 'log-plain log-tool-result-text';
  if (isError) wrapperClass += ' log-banner-error';
  else if (isWarning) wrapperClass += ' log-banner-warning';

  return (
    <div className={wrapperClass}>
      {segments.map((seg, i) => {
        if (seg.type === 'tool' && seg.label) {
          const cfg = getToolConfig(seg.label);
          return (
            <div key={i} className="log-tool-result-segment">
              <span className="log-tool-result-badge" style={{ borderColor: cfg.color, color: cfg.color }}>
                <i className={cfg.icon} style={{ marginRight: 4 }}></i>{seg.label}
              </span>
              <CollapsibleText text={seg.text} mono />
            </div>
          );
        }
        const text = seg.text;
        if (text.length > COLLAPSE_THRESHOLD) {
          return <CollapsibleText key={i} text={text} mono />;
        }
        return <div key={i} className="log-collapsible-text log-mono">{escapeHtml(text)}</div>;
      })}
    </div>
  );
}

function classifySystemMessage(content: string): { icon: string; label: string; style: string } {
  const emoji = content.match(/^([✅📋📁🛠️🎬❌🔄🛑🏁🔀📏⚠️ℹ️])/)?.[1] || '';
  if (content.startsWith('✅ Step')) {
    return { icon: 'fa-circle-check', label: 'Step Complete', style: 'log-milestone-success' };
  }
  if (content.includes('Auto-Completed')) {
    return { icon: 'fa-forward', label: 'Auto-Completed', style: 'log-milestone-warning' };
  }
  if (content.startsWith('🎬') || content.startsWith('Starting Step')) {
    return { icon: 'fa-play', label: 'Starting Step', style: 'log-milestone-info' };
  }
  if (content.includes('Stage 1') || content.includes('Complete Plan')) {
    return { icon: 'fa-clipboard-list', label: 'Plan', style: 'log-milestone-info' };
  }
  if (content.includes('Project Structure')) {
    return { icon: 'fa-sitemap', label: 'Structure', style: 'log-milestone-info' };
  }
  if (content.includes('Execution Steps') || content.includes('Stage 2')) {
    return { icon: 'fa-list', label: 'Steps', style: 'log-milestone-info' };
  }
  if (content.startsWith('❌') || content.startsWith('Task failed')) {
    return { icon: 'fa-circle-exclamation', label: 'Error', style: 'log-milestone-error' };
  }
  if (content.startsWith('🔄') || content.startsWith('Resumed') || content.startsWith('Retry')) {
    return { icon: 'fa-rotate', label: 'Retry', style: 'log-milestone-warning' };
  }
  if (content.startsWith('🛑') || content.startsWith('🏁')) {
    return { icon: 'fa-flag', label: 'Task End', style: 'log-milestone-error' };
  }
  if (content.includes('parallel group') || content.startsWith('🔀')) {
    return { icon: 'fa-layer-group', label: 'Parallel', style: 'log-milestone-info' };
  }
  if (content.includes('compacted') || content.startsWith('📏') || content.startsWith('⚠️')) {
    return { icon: 'fa-compress', label: 'Context', style: 'log-milestone-warning' };
  }
  if (content.startsWith('Initialized task')) {
    return { icon: 'fa-rocket', label: 'Initialized', style: 'log-milestone-info' };
  }
  return { icon: 'fa-server', label: 'System', style: '' };
}

function renderSystemContent(content: string) {
  const cls = classifySystemMessage(content);
  const isMilestone = cls.style ? true : false;
  const hasEmoji = /^[✅📋📁🛠️🎬❌🔄🛑🏁🔀📏⚠️ℹ️]/.test(content);
  const clean = hasEmoji ? content.replace(/^[✅📋📁🛠️🎬❌🔄🛑🏁🔀📏⚠️ℹ️]\s*/, '') : content;

  if (isMilestone) {
    return (
      <div className="log-milestone">
        <div className={`log-milestone-icon ${cls.style}`}>
          <i className={`fa-solid ${cls.icon}`}></i>
        </div>
        <div className="log-milestone-body">
          <div className="log-milestone-label">{cls.label}</div>
          <div className="log-milestone-text log-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(clean) }} />
        </div>
      </div>
    );
  }
  return (
    <div className="log-plain log-system-generic">
      <div className="log-collapsible-text">{escapeHtml(content)}</div>
    </div>
  );
}

function renderUserIntervention(content: string) {
  return (
    <div className="log-user-intervention">
      <div className="log-ui-header">
        <i className="fa-solid fa-user-pen"></i> User Intervention
      </div>
      <div className="log-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
    </div>
  );
}

function renderAssistantContent(content: string) {
  const { before, think, after } = extractThinkBlocks(content);
  const parts: React.ReactNode[] = [];

  if (before.trim()) {
    const calls = parseMultipleToolCalls(before);
    if (calls.length > 0) {
      parts.push(<div key="calls" className="log-tool-calls">{calls.map(c => renderToolCall(c.tool, c.args))}</div>);
    } else {
      const nonToolText = before.replace(/\{[^{}]*"tool"\s*:.*?\}/gs, '').trim();
      if (nonToolText) {
        parts.push(
          <div key="text" className="log-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(nonToolText) }} />
        );
      }
    }
  }

  if (think) {
    parts.push(
      <details key="think" className="log-think-block">
        <summary className="log-think-summary"><i className="fa-solid fa-brain"></i> Reasoning</summary>
        <div className="log-think-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(think) }} />
      </details>
    );
  }

  if (after.trim()) {
    const afterCalls = parseMultipleToolCalls(after);
    if (afterCalls.length > 0) {
      parts.push(<div key="after-calls" className="log-tool-calls">{afterCalls.map(c => renderToolCall(c.tool, c.args))}</div>);
    } else {
      parts.push(
        <div key="after" className="log-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(after) }} />
      );
    }
  }

  return parts.length > 0 ? <>{parts}</> : null;
}

function LogCard({ entry }: { entry: LogEntry }) {
  const step = entry.step ?? '-';
  const roleConfig: Record<string, { icon: string; label: string }> = {
    system: { icon: 'fa-server', label: 'System' },
    assistant: { icon: 'fa-robot', label: 'Assistant' },
    tool_result: { icon: 'fa-terminal', label: 'Tool Result' },
    supervisor: { icon: 'fa-shield-halved', label: 'Supervisor' },
    user_intervention: { icon: 'fa-user-pen', label: 'User Intervention' },
  };
  const cfg = roleConfig[entry.role] ?? { icon: 'fa-server', label: entry.role.replace(/_/g, ' ') };

  const body = () => {
    if (entry.role === 'assistant') return renderAssistantContent(entry.content);
    if (entry.role === 'tool_result') return renderToolResult(entry.content);
    if (entry.role === 'system') return renderSystemContent(entry.content);
    if (entry.role === 'user_intervention') return renderUserIntervention(entry.content);
    if (entry.role === 'supervisor') {
      return <div className="log-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(entry.content) }} />;
    }
    return <div className="log-collapsible-text">{escapeHtml(entry.content)}</div>;
  };

  return (
    <div className={`log-card log-role-${entry.role}`}>
      <div className="log-card-header">
        <span className="log-card-title">
          <i className={`fa-solid ${cfg.icon}`}></i>
          {cfg.label}
          {step !== '-' ? <span className="log-step-badge">Step {step}</span> : null}
        </span>
        <span className="log-card-header-right">
          {entry.llm_usage ? (
            <span className="log-usage-badge">{escapeHtml(formatLlmUsage(entry.llm_usage))}</span>
          ) : null}
        </span>
      </div>
      <div className="log-card-body">{body()}</div>
    </div>
  );
}

function FilterBar({ active, onChange, counts }: {
  active: LogFilter;
  onChange: (f: LogFilter) => void;
  counts: Record<string, number>;
}) {
  const filters: Array<{ key: LogFilter; icon: string; label: string }> = [
    { key: 'all', icon: 'fa-list', label: 'All' },
    { key: 'system', icon: 'fa-server', label: 'System' },
    { key: 'assistant', icon: 'fa-robot', label: 'Assistant' },
    { key: 'tool_result', icon: 'fa-terminal', label: 'Results' },
    { key: 'user_intervention', icon: 'fa-user-pen', label: 'Interventions' },
    { key: 'errors', icon: 'fa-circle-exclamation', label: 'Errors' },
  ];

  return (
    <div className="log-filter-bar">
      {filters.map(f => (
        <button
          key={f.key}
          className={`log-filter-btn${active === f.key ? ' active' : ''}`}
          onClick={() => onChange(f.key)}
        >
          <i className={`fa-solid ${f.icon}`}></i>
          <span>{f.label}</span>
          {counts[f.key] > 0 && <span className="log-filter-count">{counts[f.key]}</span>}
        </button>
      ))}
    </div>
  );
}

const FILTER_ROLES: Record<LogFilter, string | null> = {
  all: null,
  system: 'system',
  assistant: 'assistant',
  tool_result: 'tool_result',
  user_intervention: 'user_intervention',
  supervisor: 'supervisor',
  errors: null,
};

function isErrorEntry(entry: LogEntry): boolean {
  if (entry.role === 'tool_result') {
    return /^ERROR|LOOP DETECTED|WARNING/i.test(entry.content);
  }
  if (entry.role === 'system') {
    return /❌|failed|aborted|error/i.test(entry.content);
  }
  return false;
}

export default function LogsTab({ logs, commandOutput }: { logs: LogEntry[]; commandOutput?: string }) {
  const renderCount = ++_logsRenderCount.current;
  console.log(`[LogsTab] #${renderCount} logs=${logs.length}`);
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const [logFilter, setLogFilter] = useState<LogFilter>('all');

  const scrollToBottom = () => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  };

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      userScrolledUpRef.current = distFromBottom > SCROLL_THRESHOLD;
    };
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  const filteredLogs = useMemo(() => {
    if (logFilter === 'all') return logs;
    if (logFilter === 'errors') return logs.filter(isErrorEntry);
    return logs.filter(e => e.role === FILTER_ROLES[logFilter]);
  }, [logs, logFilter]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: logs.length, system: 0, assistant: 0, tool_result: 0, user_intervention: 0, supervisor: 0, errors: 0 };
    for (const e of logs) {
      if (e.role === 'system') c.system++;
      else if (e.role === 'assistant') c.assistant++;
      else if (e.role === 'tool_result') c.tool_result++;
      else if (e.role === 'user_intervention') c.user_intervention++;
      else if (e.role === 'supervisor') c.supervisor++;
      if (isErrorEntry(e)) c.errors++;
    }
    return c;
  }, [logs]);

  useEffect(() => {
    if (!userScrolledUpRef.current) scrollToBottom();
  }, [filteredLogs.length]);

  return (
    <div className="execution-panel" id="execution-log" ref={containerRef}>
      {filteredLogs.length === 0 ? (
        <div className="log-empty-state">
          <i className="fa-solid fa-filter"></i>
          <span>No {logFilter === 'all' ? '' : logFilter} log entries found.</span>
        </div>
      ) : (
        filteredLogs.map((entry, idx) => (
          <LogCard key={`${idx}-${entry.role}-${entry.step ?? ''}-${entry.content.slice(0, 20)}`} entry={entry} />
        ))
      )}
      {commandOutput ? (
        <div className="log-card log-role-tool_result log-command-streaming">
          <div className="log-card-header">
            <span className="log-card-title">
              <i className="fa-solid fa-terminal"></i> Command Output (Live)
              <span className="log-streaming-dot"></span>
            </span>
          </div>
          <div className="log-card-body">
            <div className="log-plain log-tool-result-text">
              {commandOutput.length > 1000 ? (
                <CollapsibleText text={commandOutput} mono />
              ) : (
                <div className="log-collapsible-text log-mono">{escapeHtml(commandOutput)}</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
      {logs.length > 10 && (
        <FilterBar active={logFilter} onChange={setLogFilter} counts={counts} />
      )}
    </div>
  );
}
