import type { FinishOutcome } from '../types';
import { getState, setState, selectTask } from '../state/store';
import { $, toggleClass } from '../utils/dom';
import { api } from '../api/client';
import { fetchTaskDetails, loadTasksList } from './tasks';

function openModal(id: string): void {
  const el = document.getElementById(id);
  if (el) {
    el.style.display = 'flex';
    el.classList.add('active');
  }
}

export function closeAllModals(): void {
  document.querySelectorAll<HTMLElement>('.modal-overlay').forEach(el => {
    el.classList.remove('active');
  });
}

export function openNewTaskModal(): void {
  openModal('modal-new-task');
  const input = $('#new-task-prompt') as HTMLTextAreaElement | null;
  input?.focus();
}

export async function submitNewTask(): Promise<void> {
  const promptEl = $('#new-task-prompt') as HTMLTextAreaElement | null;
  const prompt = promptEl?.value.trim();

  if (!prompt) {
    alert('Please write a task description.');
    return;
  }

  const modeEl = $('#new-task-mode') as HTMLSelectElement | null;
  const providerEl = $('#new-task-provider') as HTMLSelectElement | null;
  const complexityEl = $('#new-task-complexity') as HTMLSelectElement | null;
  const mode = modeEl?.value ?? 'auto';
  const provider = providerEl?.value ?? 'llamacpp';
  const complexity = complexityEl?.value ?? 'complex';

  closeAllModals();

  try {
    const task = await api.createTask({ task: prompt, mode, provider_type: provider, complexity });

    if (promptEl) promptEl.value = '';
    if (providerEl) providerEl.value = 'llamacpp';
    selectTask(task.task_id);
    await fetchTaskDetails(task.task_id);
    await loadTasksList();
  } catch (err) {
    console.error('Error creating task', err);
  }
}

export async function openPromptModal(): Promise<void> {
  try {
    const data = await api.getPrompt();
    const textarea = $('#system-prompt-text') as HTMLTextAreaElement | null;
    if (textarea) textarea.value = data.prompt ?? '';
    openModal('modal-system-prompt');
  } catch (err) {
    console.error('Error loading prompt', err);
  }
}

export async function saveSystemPrompt(): Promise<void> {
  const textarea = $('#system-prompt-text') as HTMLTextAreaElement | null;
  if (!textarea) return;

  try {
    await api.savePrompt(textarea.value);
    alert('System prompt updated!');
    closeAllModals();
  } catch (err) {
    console.error('Error saving prompt', err);
    alert('Failed to update system prompt.');
  }
}

export async function openLessonsModal(): Promise<void> {
  try {
    const data = await api.getLessons();
    const container = $('#lessons-list-container');
    if (!container) return;

    container.innerHTML = '';
    const lessons = data.lessons ?? [];

    if (!lessons.length) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; text-align: center;">No lessons learned yet.</div>';
    } else {
      for (const [i, l] of lessons.entries()) {
        const item = document.createElement('div');
        item.style.cssText = 'background: rgba(0,0,0,0.2); padding: 16px; border-radius: 8px; border: 1px solid var(--border-color); margin-bottom: 10px;';
        item.innerHTML = `
          <div style="font-weight: 700; color: #818cf8; margin-bottom: 6px;">Lesson ${i + 1}: ${l.title}</div>
          ${l.error ? `<div style="font-family: var(--font-code); font-size: 12px; color: var(--color-danger); background: rgba(239, 68, 68, 0.05); padding: 8px; border-radius: 4px; margin-bottom: 6px;">Error: ${l.error}</div>` : ''}
          <div style="font-size: 13px; color: var(--text-primary); line-height: 1.4;"><strong style="color: var(--color-success)">Fix:</strong> ${l.resolution}</div>
        `;
        container.appendChild(item);
      }
    }

    openModal('modal-lessons');
  } catch (err) {
    console.error('Error loading lessons', err);
  }
}

export function openFinishTaskModal(): void {
  setState('finishOutcome', 'completed');
  toggleClass($('#btn-outcome-completed'), 'active', true);
  toggleClass($('#btn-outcome-failed'), 'active', false);

  const reason = $('#finish-task-reason') as HTMLTextAreaElement | null;
  if (reason) reason.value = '';
  openModal('modal-finish-task');
}

export function setFinishOutcome(outcome: FinishOutcome): void {
  setState('finishOutcome', outcome);
  toggleClass($('#btn-outcome-completed'), 'active', outcome === 'completed');
  toggleClass($('#btn-outcome-failed'), 'active', outcome === 'failed');
}

export async function submitFinishTask(): Promise<void> {
  const taskId = getState('currentTaskId');
  const reasonEl = $('#finish-task-reason') as HTMLTextAreaElement | null;
  const reason = reasonEl?.value.trim();

  if (!taskId) return;
  if (!reason) {
    alert('Please provide a reason or summary for manually finishing the task.');
    return;
  }

  try {
    await api.taskAction(taskId, {
      action: 'force_complete',
      status: getState('finishOutcome'),
      reason,
    });

    closeAllModals();
    await fetchTaskDetails(taskId);
    await loadTasksList();
  } catch (err) {
    console.error('Error finishing task', err);
    alert(`Error finishing task: ${err instanceof Error ? err.message : 'Unknown'}`);
  }
}

export function initModals(): void {
  $('#btn-new-task')?.addEventListener('click', openNewTaskModal);
  $('#btn-launch-task')?.addEventListener('click', openNewTaskModal);
  $('#btn-submit-new-task')?.addEventListener('click', submitNewTask);

  $('#btn-prompt')?.addEventListener('click', openPromptModal);
  $('#btn-save-prompt')?.addEventListener('click', saveSystemPrompt);

  $('#btn-lessons')?.addEventListener('click', openLessonsModal);

  $('#btn-finish-task')?.addEventListener('click', openFinishTaskModal);
  $('#btn-submit-finish')?.addEventListener('click', submitFinishTask);
  $('#btn-outcome-completed')?.addEventListener('click', () => setFinishOutcome('completed'));
  $('#btn-outcome-failed')?.addEventListener('click', () => setFinishOutcome('failed'));

  document.querySelectorAll<HTMLElement>('.modal-close').forEach(el => {
    el.addEventListener('click', closeAllModals);
  });

  $('#btn-cancel-new-task')?.addEventListener('click', closeAllModals);
  $('#btn-cancel-prompt')?.addEventListener('click', closeAllModals);
  $('#btn-close-lessons')?.addEventListener('click', closeAllModals);
  $('#btn-cancel-finish')?.addEventListener('click', closeAllModals);

  document.querySelectorAll<HTMLElement>('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeAllModals();
    });
  });

  $('#btn-sidebar-close')?.addEventListener('click', () => {
    $('#sidebar')?.classList.remove('open');
    $('#sidebar-overlay')?.classList.remove('active');
  });

  $('#sidebar-overlay')?.addEventListener('click', () => {
    $('#sidebar')?.classList.remove('open');
    $('#sidebar-overlay')?.classList.remove('active');
  });

  $('#btn-hamburger')?.addEventListener('click', () => {
    $('#sidebar')?.classList.add('open');
    $('#sidebar-overlay')?.classList.add('active');
  });
}
