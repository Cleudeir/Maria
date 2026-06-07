import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { useTheme } from '../hooks/useTheme';

export default function Sidebar() {
  const {
    tasks, currentTaskId, batchSelectionMode, selectedTasksForDelete,
    toggleBatchSelectionMode, toggleTaskSelection, clearSelectedTasks,
    batchDeleteTasks, loadTasksList,
  } = useApp();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();

  useEffect(() => {
    const onHash = () => {
      const id = window.location.hash.replace('#', '');
      if (id === 'sidebar-overlay') {
        document.getElementById('sidebar')?.classList.remove('open');
        document.getElementById('sidebar-overlay')?.classList.remove('active');
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const openSidebar = () => {
    document.getElementById('sidebar')?.classList.add('open');
    document.getElementById('sidebar-overlay')?.classList.add('active');
  };
  const closeSidebar = () => {
    document.getElementById('sidebar')?.classList.remove('open');
    document.getElementById('sidebar-overlay')?.classList.remove('active');
  };

  const handleTaskClick = (taskId: string) => {
    navigate(`/task/${taskId}`);
    closeSidebar();
  };

  const statusClass = (s: string) => `status-${s}`;
  const statusLabel = (s: string) => s.replace(/_/g, ' ');

  const selectedCount = selectedTasksForDelete.size;

  return (
    <>
      <div className="sidebar" id="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <div className="brand-logo"><i className="fa-solid fa-brain-circuit"></i> AGENTIC</div>
            <div className="brand-badge">slm</div>
          </div>
          <button className="btn-sidebar-close" id="btn-sidebar-close" aria-label="Close sidebar" onClick={closeSidebar}>
            <i className="fa-solid fa-xmark"></i>
          </button>
        </div>
        <button className="btn-new-task" id="btn-new-task" onClick={() => {
          const el = document.getElementById('modal-new-task');
          if (el) { el.style.display = ''; el.classList.add('active'); }
        }}>
          <i className="fa-solid fa-plus"></i> New Agent Task
        </button>
        <div className="tasks-list-container">
          <div className="tasks-list-header">
            <div className="tasks-list-title">Active / Past Tasks</div>
            <button className="btn-batch-toggle" id="btn-batch-toggle" title="Batch delete mode" onClick={toggleBatchSelectionMode}>
              <i className="fa-solid fa-layer-group"></i>
            </button>
          </div>
          <div id="tasks-list">
            {tasks.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: 20 }}>No tasks found</div>
            ) : (
              tasks.map(task => {
                const isActive = task.task_id === currentTaskId;
                const isSelected = selectedTasksForDelete.has(task.task_id);
                return (
                  <div
                    key={task.task_id}
                    className={`task-item${isActive ? ' active' : ''}${isSelected ? ' selected' : ''}`}
                    data-task-id={task.task_id}
                    onClick={() => batchSelectionMode ? toggleTaskSelection(task.task_id) : handleTaskClick(task.task_id)}
                  >
                    {batchSelectionMode ? (
                      <div className="task-item-checkbox">
                        <input type="checkbox" checked={isSelected} readOnly />
                      </div>
                    ) : null}
                    <div className="task-item-content">
                      <div className="task-item-header">
                        <span className="task-item-id">{task.task_id}</span>
                        <span className={`task-item-status ${statusClass(task.status)}`}>{statusLabel(task.status)}</span>
                      </div>
                      <div className="task-item-desc" title={task.task}>{task.task}</div>
                      <div className="task-item-date">
                        <span>Step: {task.step}</span>
                        <span>{task.created_at ?? ''}</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
          <div className="batch-actions" id="batch-actions" style={{ display: batchSelectionMode ? 'flex' : 'none' }}>
            <button className="btn-batch-delete" id="btn-batch-delete" onClick={batchDeleteTasks}>
              <i className="fa-solid fa-trash-can"></i> Delete Selected (<span id="selected-count">{selectedCount}</span>)
            </button>
          </div>
        </div>
        <div className="sidebar-footer">
          <button className="btn-footer" id="btn-theme-toggle" onClick={toggle}>
            <i className={`fa-solid ${theme === 'dark' ? 'fa-sun' : 'fa-moon'}`}></i> {theme === 'dark' ? 'Light' : 'Dark'} Mode
          </button>
          <button className="btn-footer" id="btn-prompt">
            <i className="fa-solid fa-sliders"></i> Prompt
          </button>
          <button className="btn-footer" id="btn-lessons">
            <i className="fa-solid fa-graduation-cap"></i> Lessons
          </button>
        </div>
      </div>
      <div className="sidebar-overlay" id="sidebar-overlay" onClick={closeSidebar}></div>
    </>
  );
}
