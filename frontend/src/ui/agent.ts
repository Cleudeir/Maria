import type { Task } from '../types';
import { $, hide, show } from '../utils/dom';
import { getToolConfig } from '../utils/formatters';

export function renderAgentInfo(task: Task): void {
  const stepEl = $('#agent-current-step');
  const statusEl = $('#agent-current-status');
  const modeEl = $('#agent-mode');

  if (stepEl) stepEl.textContent = String(task.step ?? '-');
  if (statusEl) statusEl.textContent = task.status.replace(/_/g, ' ');

  const mode = task.mode ?? 'auto';
  if (modeEl) modeEl.textContent = mode === 'step' ? 'Step-by-Step' : 'Auto-run';
}

export function renderIntervention(task: Task): void {
  const consoleEl = $('#intervention-console');
  if (!consoleEl) return;

  if (task.status !== 'awaiting_intervention') {
    hide(consoleEl);
    return;
  }

  show(consoleEl, 'flex');

  const proposed = task.proposed_tool;
  const container = $('#proposed-tool-container');
  const approveBtn = $('#btn-approve-tool');
  const modifyBtn = $('#btn-modify-tool');

  if (proposed?.name) {
    show(container, 'block');
    const cfg = getToolConfig(proposed.name);
    const nameEl = $('#proposed-tool-name');
    if (nameEl) {
      nameEl.innerHTML = `<i class="${cfg.icon}" style="color:${cfg.color}"></i> ${proposed.name}`;
    }

    const argsEl = $('#proposed-tool-args') as HTMLTextAreaElement | null;
    if (argsEl) argsEl.value = JSON.stringify(proposed.args, null, 2);

    if (approveBtn) {
      approveBtn.innerHTML = '<i class="fa-solid fa-check"></i> Approve & Step';
      show(approveBtn, 'flex');
    }
    if (modifyBtn) show(modifyBtn, 'flex');
  } else {
    hide(container);
    hide(approveBtn);
    hide(modifyBtn);
  }
}
