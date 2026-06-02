import { useState, useEffect } from 'react';
import { api } from '../../api/client';

export default function SystemPromptModal() {
  const [prompt, setPrompt] = useState('');

  useEffect(() => {
    const observer = new MutationObserver(() => {
      const el = document.getElementById('modal-system-prompt');
      if (el && el.classList.contains('active')) {
        api.getPrompt().then(data => setPrompt(data.prompt ?? '')).catch(() => {});
      }
    });
    const el = document.getElementById('modal-system-prompt');
    if (el) observer.observe(el, { attributes: true, attributeFilter: ['class', 'style'] });
    return () => observer.disconnect();
  }, []);

  const close = () => {
    const el = document.getElementById('modal-system-prompt');
    if (el) {
      el.classList.remove('active');
      el.style.display = 'none';
    }
  };

  const save = async () => {
    try {
      await api.savePrompt(prompt);
      alert('System prompt updated!');
      close();
    } catch {
      alert('Failed to update system prompt.');
    }
  };

  return (
    <div className="modal-overlay" id="modal-system-prompt">
      <div className="modal-box" style={{ width: '700px' }}>
        <div className="modal-header">
          <div className="modal-title">Edit System Prompt Memory</div>
          <i className="fa-solid fa-xmark modal-close" id="close-modal-prompt" onClick={close}></i>
        </div>
        <div className="form-group">
          <label className="form-label">Current Guidelines Prompt</label>
          <textarea className="form-textarea" style={{ height: '350px', fontFamily: 'var(--font-code)', fontSize: '12px' }} value={prompt} onChange={e => setPrompt(e.target.value)}></textarea>
        </div>
        <div className="modal-footer">
          <button className="btn-modal" onClick={close}>Cancel</button>
          <button className="btn-modal btn-modal-submit" onClick={save}>Save Prompts</button>
        </div>
      </div>
    </div>
  );
}
