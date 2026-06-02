import { useState } from 'react';
import type { FinishOutcome } from '../../types';
import { useApp } from '../../context/AppContext';
import { api } from '../../api/client';

export default function FinishTaskModal() {
  const { finishOutcome, setFinishOutcome } = useApp();
  const [reason, setReason] = useState('');

  const close = () => {
    const el = document.getElementById('modal-finish-task');
    if (el) {
      el.classList.remove('active');
      el.style.display = 'none';
    }
  };

  const submit = async () => {
    if (!reason.trim()) {
      alert('Please provide a reason or summary for manually finishing the task.');
      return;
    }
    try {
      await api.taskAction('', { action: 'force_complete', status: finishOutcome, reason: reason.trim() });
      close();
    } catch (err) {
      alert(`Error finishing task: ${err instanceof Error ? err.message : 'Unknown'}`);
    }
  };

  return (
    <div className="modal-overlay" id="modal-finish-task">
      <div className="modal-box">
        <div className="modal-header">
          <div className="modal-title">Manually Finish Task</div>
          <i className="fa-solid fa-xmark modal-close" id="close-modal-finish" onClick={close}></i>
        </div>
        <div className="form-group">
          <label className="form-label">Task Status Outcome</label>
          <div className="outcome-selector-group">
            <button type="button" className={`btn-outcome${finishOutcome === 'completed' ? ' active' : ''}`} onClick={() => setFinishOutcome('completed')}>
              <i className="fa-solid fa-circle-check"></i> Completed (Success)
            </button>
            <button type="button" className={`btn-outcome${finishOutcome === 'failed' ? ' active' : ''}`} onClick={() => setFinishOutcome('failed')}>
              <i className="fa-solid fa-circle-xmark"></i> Failed (Failure)
            </button>
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">Completion Summary / Reason</label>
          <textarea className="form-textarea" placeholder="Explain why you are finishing this task manually..." value={reason} onChange={e => setReason(e.target.value)}></textarea>
        </div>
        <div className="modal-footer">
          <button className="btn-modal" onClick={close}>Cancel</button>
          <button className="btn-modal btn-modal-submit" onClick={submit}>Finish Task</button>
        </div>
      </div>
    </div>
  );
}
