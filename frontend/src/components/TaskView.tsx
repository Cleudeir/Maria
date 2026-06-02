import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import type { TabName, EditorTab } from '../types';
import StreamingTab from './StreamingTab';
import FilesTab from './FilesTab';
import AgentTab from './AgentTab';
import WorkspaceTab from './WorkspaceTab';
import LogsTab from './LogsTab';
import ServerList from './ServerList';
import SupervisionBanner from './SupervisionBanner';

const _taskRenderCount = { current: 0 };

export default function TaskView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const renderCount = ++_taskRenderCount.current;
  const {
    currentTask, currentTab, setCurrentTab,
    selectTaskById, fetchTaskDetails, activeTaskStatus,
    loadTasksList, stopTask,
  } = useApp();

  useEffect(() => {
    console.log(`[TaskView] #${renderCount} MOUNT id=${id} taskId=${currentTask?.task_id}`);
    if (id) {
      selectTaskById(id);
    }
    return () => console.log(`[TaskView] #${renderCount} UNMOUNT`);
  }, [id, selectTaskById, currentTask?.task_id]);

  const handleTabClick = useCallback((tab: TabName) => {
    setCurrentTab(tab);
  }, [setCurrentTab]);

  const task = currentTask;
  if (!task) {
    console.log(`[TaskView] #${renderCount} NO TASK`);
    return <div className="task-view" id="task-view"></div>;
  }

  console.log(`[TaskView] #${renderCount} RENDER step=${task.step} stage=${task.stage} status=${task.status}`);

  const statusLabel = (s: string) => s.replace(/_/g, ' ');
  const statusClass = (s: string) => `task-header-badge status-${s}`;

  const isComplete = task.status === 'completed';
  const isRunning = task.status === 'running' || task.status === 'processando';
  const isFailed = task.status === 'failed';

  const tabButtons: Array<{ key: TabName; icon: string; label: string }> = [
    { key: 'logs', icon: 'fa-scroll', label: 'Logs' },
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
            <span className={statusClass(task.status)}>{statusLabel(task.status)}</span>
            <span className="task-header-step" id="active-task-step">Step: {task.step}</span>
            {task.files_progress != null ? (
              <span className="task-header-progress" id="task-files-progress">
                <i className="fa-solid fa-file"></i> {task.files_progress}%
              </span>
            ) : null}
          </div>
        </div>
        <div className="task-header-actions">
          {isRunning ? (
            <button className="btn-action btn-stop" id="btn-stop-task" onClick={stopTask}>
              <i className="fa-solid fa-stop"></i> Stop
            </button>
          ) : null}
          <button className="btn-action" id="btn-preview-html" style={{ display: isComplete ? 'inline-flex' : 'none' }}>
            <i className="fa-solid fa-eye"></i> Preview
          </button>
          <button className="btn-action" id="btn-test-server" style={{ display: 'none' }}>
            <i className="fa-solid fa-server"></i> Test Server
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
                <i className={`fa-solid ${t.icon}`}></i><span className="tab-label"> {t.label}</span>
                {t.key === 'agent' && isFailed ? (
                  <i className="fa-solid fa-circle-exclamation tab-error-badge" id="agent-error-badge"></i>
                ) : null}
              </button>
            ))}
          </div>

          <div className={`tab-content${currentTab === 'logs' ? ' active' : ''}`} id="tab-logs">
            <LogsTab logs={task.execution_log ?? []} commandOutput={task.current_command_output} />
          </div>
          <div className={`tab-content${currentTab === 'streaming' ? ' active' : ''}`} id="tab-streaming">
            <StreamingTab
              isStreaming={task.is_streaming ?? false}
              content={task.current_streaming_response}
            />
          </div>
          <div className={`tab-content${currentTab === 'created' ? ' active' : ''}`} id="tab-created">
            <FilesTab
              files={task.created_files ?? []}
              toCreateFiles={task.project_files_to_create ?? []}
              filesProgress={task.files_progress ?? 0}
            />
          </div>
          <div className={`tab-content${currentTab === 'agent' ? ' active' : ''}`} id="tab-agent">
            <AgentTab task={task} />
          </div>
          <div className={`tab-content${currentTab === 'workspace' ? ' active' : ''}`} id="tab-workspace">
            <WorkspaceTab taskId={task.task_id} fileTree={task.file_tree} />
          </div>
        </div>
      </div>

      <div className="task-chat-bar" id="task-chat-bar" style={{ display: 'flex' }}>
        <ChatBar />
      </div>
    </div>
  );
}

function ChatBar() {
  const [value, setValue] = useState('');
  const { sendChatPrompt } = useApp();

  const handleSend = () => {
    if (!value.trim()) return;
    sendChatPrompt(value.trim());
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
