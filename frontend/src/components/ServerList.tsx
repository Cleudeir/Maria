import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import type { HttpServerInfo } from '../types';
import { escapeHtml } from '../utils/formatters';

export default function ServerList({ taskId }: { taskId: string }) {
  const [servers, setServers] = useState<HttpServerInfo[]>([]);

  const load = useCallback(async () => {
    try {
      const res = await api.listServers();
      setServers((res.servers ?? []).filter(s => s.task_id === taskId));
    } catch {}
  }, [taskId]);

  useEffect(() => {
    load();
  }, [load]);

  const stopServer = async (serverId: string) => {
    if (!confirm(`Stop test server ${serverId}?`)) return;
    try {
      await api.stopServer(serverId, taskId);
      await load();
    } catch {
      alert('Failed to stop the HTTP server.');
    }
  };

  if (servers.length === 0) return null;

  return (
    <div className="task-servers-card" id="task-servers-card">
      <div className="task-servers-header">
        <i className="fa-solid fa-server"></i>
        <span>Active Test Servers</span>
      </div>
      <div className="task-servers-list" id="task-servers-list">
        {servers.map(s => (
          <div key={s.server_id} className="task-server-row" data-server-id={escapeHtml(s.server_id)}>
            <a className="task-server-url" href={escapeHtml(s.url)} target="_blank" rel="noreferrer">
              <i className="fa-solid fa-up-right-from-square"></i> {escapeHtml(s.url)}
            </a>
            <span className="task-server-path" title={escapeHtml(s.path)}>{escapeHtml(s.path)}</span>
            <button className="btn-server-stop" onClick={() => stopServer(s.server_id)} title="Stop this server">
              <i className="fa-solid fa-stop"></i>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
