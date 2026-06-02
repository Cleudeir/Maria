import type { Task } from '../types';
import { useApp } from '../context/AppContext';
import { useNavigate } from 'react-router-dom';

export default function AgentTab({ task }: { task: Task }) {
  const { stopTask, continueTask, deleteTask } = useApp();
  const navigate = useNavigate();

  const isFail = task.status === 'failed';
  const isRunning = task.status === 'running' || task.status === 'processando';

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this task? All workspace files and logs will be permanently removed.')) return;
    await deleteTask();
    navigate('/task');
  };

  return (
    <div className="agent-panel">
      <div className="agent-status-card">
        <div className="agent-status-header">
          <i className="fa-solid fa-robot"></i>
          <span>Agent Status</span>
        </div>
        <div className="agent-status-body">
          <div className="agent-info-row">
            <span className="agent-info-label">Current Step:</span>
            <span className="agent-info-value">{task.step ?? '-'}</span>
          </div>
          <div className="agent-info-row">
            <span className="agent-info-label">Status:</span>
            <span className="agent-info-value">{task.status.replace(/_/g, ' ')}</span>
          </div>
          <div className="agent-info-row">
            <span className="agent-info-label">Mode:</span>
            <span className="agent-info-value">Auto-run</span>
          </div>
        </div>
      </div>

      {isFail && task.details ? (
        <div className="task-motivo" id="task-motivo">
          <div className="task-motivo-icon"><i className="fa-solid fa-circle-exclamation"></i></div>
          <div className="task-motivo-content">
            <div className="task-motivo-label">Motivo da Falha:</div>
            <div className="task-motivo-text" id="task-motivo-text">{task.details}</div>
          </div>
        </div>
      ) : null}

      <div className="agent-actions">
        {isFail ? (
          <button className="btn-action" id="btn-continue-task" onClick={continueTask}>
            <i className="fa-solid fa-rotate"></i> Continue
          </button>
        ) : null}
        <button className="btn-action danger" onClick={handleDelete}>
          <i className="fa-solid fa-trash-can"></i> Delete
        </button>
      </div>
    </div>
  );
}
