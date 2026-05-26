import type { Task } from '../types';
import { $, hide, show } from '../utils/dom';
import { escapeHtml } from '../utils/formatters';

export function renderStreaming(task: Task): void {
  const panel = $('#streaming-panel');
  const content = $('#streaming-content');
  const empty = $('#streaming-empty');
  if (!panel || !content) return;

  if (!task.is_streaming) {
    hide(panel);
    content.innerHTML = '';
    show(empty, 'flex');
    return;
  }

  show(panel, 'flex');
  hide(empty);

  let text = task.current_streaming_response ?? 'Waiting for generation...';
  if (text.length > 200) {
    text = '...' + text.slice(-200);
  }

  content.innerHTML = escapeHtml(text).replace(/\n/g, '<br>');
}
