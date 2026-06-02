import { useState, useEffect } from 'react';
import { api } from '../../api/client';

export default function LessonsModal() {
  const [lessons, setLessons] = useState<Array<{ title: string; error?: string; resolution: string }>>([]);

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const el = document.getElementById('modal-lessons');
      if (el && el.classList.contains('active')) {
        api.getLessons().then(data => setLessons(data.lessons ?? [])).catch(() => {});
      }
    });
    const el = document.getElementById('modal-lessons');
    if (el) observer.observe(el, { attributes: true, attributeFilter: ['class', 'style'] });
    return () => observer.disconnect();
  }, []);

  const close = () => {
    const el = document.getElementById('modal-lessons');
    if (el) {
      el.classList.remove('active');
      el.style.display = 'none';
    }
  };

  return (
    <div className="modal-overlay" id="modal-lessons">
      <div className="modal-box" style={{ width: '700px' }}>
        <div className="modal-header">
          <div className="modal-title">Lessons Learned Memory</div>
          <i className="fa-solid fa-xmark modal-close" id="close-modal-lessons" onClick={close}></i>
        </div>
        <div className="form-group" style={{ maxHeight: '400px', overflowY: 'auto' }} id="lessons-list-container">
          {lessons.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center' }}>No lessons learned yet.</div>
          ) : (
            lessons.map((l, i) => (
              <div key={i} style={{ background: 'rgba(0,0,0,0.2)', padding: 16, borderRadius: 8, border: '1px solid var(--border-color)', marginBottom: 10 }}>
                <div style={{ fontWeight: 700, color: '#818cf8', marginBottom: 6 }}>Lesson {i + 1}: {l.title}</div>
                {l.error ? <div style={{ fontFamily: 'var(--font-code)', fontSize: 12, color: 'var(--color-danger)', background: 'rgba(239, 68, 68, 0.05)', padding: 8, borderRadius: 4, marginBottom: 6 }}>Error: {l.error}</div> : null}
                <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.4 }}><strong style={{ color: 'var(--color-success)' }}>Fix:</strong> {l.resolution}</div>
              </div>
            ))
          )}
        </div>
        <div className="modal-footer">
          <button className="btn-modal" onClick={close}>Close</button>
        </div>
      </div>
    </div>
  );
}
