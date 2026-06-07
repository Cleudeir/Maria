import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import type { TabName } from '../types';
import StreamingTab from './StreamingTab';
import FilesTab from './FilesTab';
import AgentTab from './AgentTab';
import WorkspaceTab from './WorkspaceTab';
import TimelineTab from './TimelineTab';
import ServerList from './ServerList';
import { api } from '../api/client';

export default function TaskView() {
  const { id } = useParams();
  const {
    currentTask, currentTab, setCurrentTab,
    selectTaskById, stopTask,
    setEditingFilePath, setEditorTab,
  } = useApp();
  const fetchedIdRef = useRef<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (id && id !== fetchedIdRef.current) {
      fetchedIdRef.current = id;
      setLoadError(null);
      selectTaskById(id).catch((err) => {
        console.error('[TaskView] selectTaskById failed', err);
        setLoadError(err?.message || String(err));
      });
    }
  }, [id, selectTaskById]);

  const handleTabClick = useCallback((tab: TabName) => {
    setCurrentTab(tab);
  }, [setCurrentTab]);

  const handleRetry = useCallback(() => {
    fetchedIdRef.current = null;
    setLoadError(null);
    if (id) selectTaskById(id);
  }, [id, selectTaskById]);

  const handlePreview = useCallback(async () => {
    if (!currentTask) return;
    try {
      const { html_files } = await api.getHtmlFiles(currentTask.task_id);
      if (html_files.length === 0) return;
      setEditingFilePath(`output/${html_files[0]}`);
      setEditorTab('preview');
      setCurrentTab('workspace');
    } catch {}
  }, [currentTask, setEditingFilePath, setEditorTab, setCurrentTab]);

  if (!currentTask) {
    return (
      <div className="task-view task-view--loading" id="task-view">
        {loadError ? (
          <>
            <i className="fa-solid fa-circle-exclamation task-view-error-icon"></i>
            <div className="task-view-error-text">Failed to load task: {loadError}</div>
            <button className="btn-action" onClick={handleRetry}>
              <i className="fa-solid fa-rotate"></i> Retry
            </button>
          </>
        ) : (
          <>
            <i className="fa-solid fa-spinner fa-spin task-view-spinner"></i>
            <div>Loading task {id ? `(${id})` : ''}…</div>
          </>
        )}
      </div>
    );
  }

  const task = currentTask;
  const isComplete = task.status === 'completed';
  const isRunning = task.status === 'running' || task.status === 'processando';
  const isFailed = task.status === 'failed';

  const tabButtons: Array<{ key: TabName; icon: string; label: string }> = [
    { key: 'logs', icon: 'fa-stream', label: 'Timeline' },
    { key: 'streaming', icon: 'fa-bolt', label: 'Streaming' },
    { key: 'created', icon: 'fa-file-code', label: 'Files' },
    { key: 'agent', icon: 'fa-robot', label: 'Agent' },
    { key: 'workspace', icon: 'fa-folder-tree', label: 'Workspace Files' },
  ];

  return (
    <div className="task-view" id="task-view">
      <div className="task-header">
        <div className="task-header-left">
          <div className="task-header-title" id="active-task-desc">{task.task}</div>
          <div className="task-header-meta">
            <span className={`task-header-badge status-${task.status}`}>
              {task.status.replace(/_/g, ' ')}
            </span>
            <span className="task-header-step" id="active-task-step">Step: {task.step}</span>
            {task.files_progress != null && (
              <span className="task-header-progress" id="task-files-progress">
                <i className="fa-solid fa-file"></i> {task.files_progress}%
              </span>
            )}
          </div>
        </div>
        <div className="task-header-actions">
          {isRunning && (
            <button className="btn-action btn-stop" id="btn-stop-task" onClick={stopTask}>
              <i className="fa-solid fa-stop"></i> Stop
            </button>
          )}
          <button
            className="btn-action"
            id="btn-preview-html"
            style={{ display: isComplete ? 'inline-flex' : 'none' }}
            onClick={handlePreview}
          >
            <i className="fa-solid fa-eye"></i> Preview
          </button>
        </div>
        <ServerList taskId={task.task_id} />
      </div>

      <div className="workspace-split">
        <div className="left-panel">
          <div className="tab-navigation">
            {tabButtons.map(t => (
              <button
                key={t.key}
                className={`tab-btn${currentTab === t.key ? ' active' : ''}`}
                data-tab={t.key}
                onClick={() => handleTabClick(t.key)}
              >
                <i className={`fa-solid ${t.icon}`}></i>
                <span className="tab-label"> {t.label}</span>
                {t.key === 'agent' && isFailed && (
                  <i className="fa-solid fa-circle-exclamation tab-error-badge" id="agent-error-badge"></i>
                )}
              </button>
            ))}
          </div>

          {currentTab === 'logs' && (
            <div className="tab-content active" id="tab-logs" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <TimelineTab logs={task.execution_log ?? []} />
            </div>
          )}
          {currentTab === 'streaming' && (
            <div className="tab-content active" id="tab-streaming" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <StreamingTab
                isStreaming={task.is_streaming ?? false}
                content={task.current_streaming_response}
              />
            </div>
          )}
          {currentTab === 'created' && (
            <div className="tab-content active" id="tab-created" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <FilesTab
                files={task.created_files ?? []}
                toCreateFiles={task.project_files_to_create ?? []}
                filesProgress={task.files_progress ?? 0}
              />
            </div>
          )}
          {currentTab === 'agent' && (
            <div className="tab-content active" id="tab-agent" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <AgentTab task={task} />
            </div>
          )}
          {currentTab === 'workspace' && (
            <div className="tab-content active" id="tab-workspace" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <WorkspaceTab taskId={task.task_id} fileTree={task.file_tree} />
            </div>
          )}
        </div>
      </div>

      <div className="task-chat-bar" id="task-chat-bar">
        <ChatBar />
      </div>
    </div>
  );
}

function ChatBar() {
  const [value, setValue] = useState('');
  const { sendChatPrompt } = useApp();

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    sendChatPrompt(trimmed);
    setValue('');
  };

  return (
    <>
      <textarea
        className="chat-bar-input"
        placeholder="Send a new instruction to the agent..."
        rows={2}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
      />
      <button className="btn-chat-send" onClick={handleSend}>
        <i className="fa-solid fa-paper-plane"></i>
      </button>
    </>
  );
}
