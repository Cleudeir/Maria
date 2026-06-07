import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../../context/AppContext';
import { api } from '../../api/client';

export default function NewTaskModal() {
  const [prompt, setPrompt] = useState('');
  const [mode, setMode] = useState('auto');
  const [complexity, setComplexity] = useState('complex');
  const [provider, setProvider] = useState('llamacpp');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { selectTask, loadTasksList, fetchTaskDetails } = useApp();
  const navigate = useNavigate();

  const close = () => {
    const el = document.getElementById('modal-new-task');
    if (el) {
      el.classList.remove('active');
      el.style.display = 'none';
    }
  };

  const handleSubmit = async () => {
    if (!prompt.trim()) {
      setError('Please write a task description.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const task = await api.createTask({
        task: prompt.trim(),
        mode,
        provider_type: provider,
        complexity,
      });
      close();
      setPrompt('');
      selectTask(task.task_id);
      await fetchTaskDetails(task.task_id);
      await loadTasksList();
      navigate(`/task/${task.task_id}`);
    } catch (err) {
      setError(`Failed to create task: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" id="modal-new-task">
      <div className="modal-box">
        <div className="modal-header">
          <div className="modal-title">Create New Agent Task</div>
          <i className="fa-solid fa-xmark modal-close" id="close-modal-new-task" onClick={close}></i>
        </div>
        {error ? <div className="form-error" id="new-task-error">{error}</div> : null}
        <div className="form-group">
          <label className="form-label">What should Agentic do?</label>
          <textarea className="form-textarea" placeholder="e.g. Write a Python function to compute the N-th prime number..." value={prompt} onChange={e => setPrompt(e.target.value)}></textarea>
        </div>
        <div className="form-group">
          <label className="form-label">Initial Execution Mode</label>
          <select className="form-select" value={mode} onChange={e => setMode(e.target.value)}>
            <option value="auto">Auto-run (fully autonomous)</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">Task Complexity</label>
          <select className="form-select" value={complexity} onChange={e => setComplexity(e.target.value)}>
            <option value="simple">Simple - Do exactly what is asked, no extra architecture</option>
            <option value="complex">Complex - Full implementation with proper architecture</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">Provider</label>
          <select className="form-select" value={provider} onChange={e => setProvider(e.target.value)}>
            <option value="llamacpp">LlamaCpp - Node 1 (192.168.20.180)</option>
            <option value="llamacpp_2">LlamaCpp - Node 2 (192.168.20.181)</option>
          </select>
        </div>
        <div className="modal-footer">
          <button className="btn-modal" onClick={close}>Cancel</button>
          <button className="btn-modal btn-modal-submit" disabled={loading} onClick={handleSubmit}>
            {loading ? <i className="fa-solid fa-spinner fa-spin"></i> : null} Launch Task
          </button>
        </div>
      </div>
    </div>
  );
}
