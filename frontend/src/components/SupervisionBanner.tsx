import type { Task } from '../types';
import { formatDate } from '../utils/formatters';

export default function SupervisionBanner({ task }: { task: Task }) {
  const showBanner =
    (task.status === 'completed' || task.status === 'failed') &&
    task.supervision_status === 'reviewed' &&
    (task.supervision_review_summary || task.supervision_reason);

  if (!showBanner) return null;

  const hasErrors = task.errors_encountered?.length;

  return (
    <div className="supervision-card" id="supervision-banner">
      <div className="supervision-icon"><i className="fa-solid fa-shield-halved"></i></div>
      <div className="supervision-info">
        <div className="supervision-heading">
          {hasErrors ? '🛡️ Supervisor agindo após erro' : 'Supervisor Final Analysis'}
        </div>
        <div className="supervision-meta-row">
          <span className="supervision-pill status-reviewed">REVIEWED</span>
          {task.supervision_last_review ? (
            <span className="supervision-timestamp">Reviewed: {formatDate(task.supervision_last_review)}</span>
          ) : null}
        </div>
        <div className="supervision-reason">{task.supervision_reason ?? 'No supervisor reasoning available.'}</div>
        <div className="supervision-extra" id="supervision-extra">{task.supervision_review_summary ?? ''}</div>
      </div>
    </div>
  );
}
