import { useEffect } from 'react';
import { useApp } from '../context/AppContext';

export default function HomeView() {
  const { dashboard, refreshDashboard, deselectTask } = useApp();

  useEffect(() => {
    deselectTask();
    refreshDashboard();
  }, []);

  return (
    <div className="home-view" id="home-view">
      <div className="home-logo">🤖</div>
      <div className="home-title">Agentic Console</div>
      <div className="home-subtitle">Welcome to the self-improving coding assistant dashboard. Run, monitor, and interact with agent tasks.</div>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value" id="stat-total">{dashboard?.total_tasks ?? 0}</div>
          <div className="stat-label">Total Tasks</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" id="stat-rate">{dashboard?.success_rate ?? 0}%</div>
          <div className="stat-label">Success Rate</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" id="stat-running">{dashboard?.running ?? 0}</div>
          <div className="stat-label">Running</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" id="stat-lessons">{dashboard?.lessons_count ?? 0}</div>
          <div className="stat-label">Lessons Stored</div>
        </div>
      </div>
      <button className="btn-action" id="btn-launch-task" onClick={() => {
        const el = document.getElementById('modal-new-task');
        if (el) { el.style.display = ''; el.classList.add('active'); }
      }}>
        <i className="fa-solid fa-bolt"></i> Launch First Task
      </button>
    </div>
  );
}
