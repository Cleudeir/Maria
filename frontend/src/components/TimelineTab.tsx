import { useEffect, useRef } from 'react';
import type { LogEntry } from '../types';

const ROLE_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  system:            { label: 'System',         color: '#6366f1', icon: 'fa-server' },
  assistant:         { label: 'Assistant',      color: '#10b981', icon: 'fa-robot' },
  tool_result:       { label: 'Tool Result',    color: '#f59e0b', icon: 'fa-terminal' },
  user_intervention: { label: 'User',           color: '#ec4899', icon: 'fa-user-pen' },
  supervisor:        { label: 'Supervisor',     color: '#8b5cf6', icon: 'fa-shield-halved' },
};

function getConfig(role: string) {
  return ROLE_CONFIG[role] ?? { label: role, color: '#94a3b8', icon: 'fa-circle' };
}

export default function TimelineTab({ logs }: { logs: LogEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs.length]);

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
        padding: '8px 16px', borderBottom: '1px solid var(--border-color)',
        background: 'var(--bg-surface)', flexShrink: 0, color: 'var(--text-muted)',
      }}>
        <i className="fa-solid fa-stream"></i>
        <span>{logs.length} log entries</span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 16px' }}>
        {logs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            <i className="fa-solid fa-stream" style={{ fontSize: 32, opacity: 0.4 }}></i>
            <p style={{ marginTop: 8 }}>No execution logs yet</p>
          </div>
        ) : (
          <div style={{ maxWidth: 900, margin: '0 auto' }}>
            {logs.map((entry, idx) => (
              <LogNode key={idx} entry={entry} index={idx} isLast={idx === logs.length - 1} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}

function LogNode({ entry, index, isLast }: { entry: LogEntry; index: number; isLast: boolean }) {
  const cfg = getConfig(entry.role);
  const isError = entry.role === 'tool_result' && /error|failed|aborted/i.test(entry.content);
  const nodeColor = isError ? '#ef4444' : cfg.color;

  return (
    <div style={{ display: 'flex', gap: 14, position: 'relative', paddingBottom: isLast ? 0 : 20 }}>
      {/* Timeline rail */}
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        flexShrink: 0, width: 36, position: 'relative',
      }}>
        <div style={{
          fontSize: 9, fontWeight: 700, color: 'var(--text-muted)',
          fontFamily: 'var(--font-code)', marginBottom: 4, letterSpacing: 0.5,
        }}>
          #{String(index + 1).padStart(3, '0')}
        </div>
        <div style={{
          width: 28, height: 28, borderRadius: '50%',
          background: nodeColor, color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, zIndex: 1, position: 'relative',
          boxShadow: `0 0 0 3px ${nodeColor}22`,
        }}>
          <i className={`fa-solid ${cfg.icon}`}></i>
        </div>
        {!isLast && (
          <div style={{
            flex: 1, width: 2, marginTop: 2,
            background: `linear-gradient(to bottom, ${nodeColor}44, transparent)`,
            minHeight: 16,
          }} />
        )}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0, paddingTop: 1 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, flexWrap: 'wrap',
        }}>
          <span style={{
            fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
            letterSpacing: 0.5, color: nodeColor,
            padding: '1px 7px', borderRadius: 3, background: `${nodeColor}15`,
          }}>
            {cfg.label}
          </span>
          {entry.step != null && entry.step > 0 && (
            <span style={{
              fontSize: 9, fontFamily: 'var(--font-code)', color: 'var(--text-muted)',
              padding: '1px 5px', borderRadius: 3, border: '1px solid var(--border-color)',
            }}>
              Step {entry.step}
            </span>
          )}
        </div>
        <div style={{
          background: isError ? `${nodeColor}08` : 'var(--bg-surface)',
          border: `1px solid ${isError ? `${nodeColor}30` : 'var(--border-color)'}`,
          borderLeft: `3px solid ${nodeColor}`,
          borderRadius: 8, padding: 10,
          fontSize: 13, lineHeight: 1.5,
          color: 'var(--text-primary)', wordBreak: 'break-word', overflow: 'hidden',
        }}>
          {entry.role === 'tool_result' ? (
            <pre style={{
              margin: 0, fontFamily: 'var(--font-code)', fontSize: 12,
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              color: isError ? '#ef4444' : 'var(--text-primary)',
              maxHeight: 300, overflowY: 'auto',
            }}>
              {entry.content}
            </pre>
          ) : (
            <div style={{ whiteSpace: 'pre-wrap' }}>{entry.content}</div>
          )}
        </div>
      </div>
    </div>
  );
}
