import type { TaskStatus } from '../types';
import { getState, setState, selectTask, deselectTask, resetTaskState } from '../state/store';
import { $, hide, show } from '../utils/dom';
import { formatDate } from '../utils/formatters';
import { api } from '../api/client';
import { renderLogs } from '../ui/logs';
import { renderStreaming } from '../ui/streaming';
import { renderAgentInfo, renderIntervention } from '../ui/agent';
import { renderFileTree } from '../ui/filetree';
import { closeEditor } from '../ui/editor';

let lastTasksJson = '';
let lastDetailsJson = '';

function statusClass(status: string): string {
  return `status-${status}`;
}

function statusLabel(status: string): string {
  return status.replace(/_/g, ' ');
}

export async function loadTasksList(): Promise<void> {
  try {
    const tasks = await api.listTasks();

    const activeTask = tasks.find(t => t.task_id === getState('currentTaskId'));
    setState('activeTaskStatus', activeTask?.status ?? null);

    const json = `${getState('currentTaskId')}|${JSON.stringify(tasks)}`;
    if (json === lastTasksJson) return;
    lastTasksJson = json;

    const list = $('#tasks-list');
    if (!list) return;

    if (!tasks.length) {
      list.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; text-align: center; padding: 20px;">No tasks found</div>';
      return;
    }

    list.innerHTML = '';

    for (const task of tasks) {
      const isActive = task.task_id === getState('currentTaskId');
      const item = document.createElement('div');
      item.className = `task-item${isActive ? ' active' : ''}`;
      item.innerHTML = `
        <div class="task-item-header">
          <span class="task-item-id">${task.task_id}</span>
          <span class="task-item-status ${statusClass(task.status)}">${statusLabel(task.status)}</span>
        </div>
        <div class="task-item-desc" title="${task.task}">${task.task}</div>
        <div class="task-item-date">
          <span>Step: ${task.step}</span>
          <span>${task.created_at ?? ''}</span>
        </div>
      `;
      item.addEventListener('click', () => selectTaskById(task.task_id));
      list.appendChild(item);
    }
  } catch (err) {
    console.error('Error loading tasks', err);
  }
}

export async function refreshDashboard(): Promise<void> {
  try {
    const data = await api.dashboard();
    const total = $('#stat-total');
    const rate = $('#stat-rate');
    const running = $('#stat-running');
    const lessons = $('#stat-lessons');
    if (total) total.textContent = String(data.stats.total_tasks);
    if (rate) rate.textContent = `${data.stats.success_rate}%`;
    if (running) running.textContent = String(data.stats.running);
    if (lessons) lessons.textContent = String(data.stats.lessons_count);
  } catch (err) {
    console.error('Error refreshing dashboard', err);
  }
}

async function selectTaskById(taskId: string): Promise<void> {
  if (getState('currentTaskId') === taskId) return;

  selectTask(taskId);
  closeEditor();
  toggleSidebar(false);

  const welcome = $('#welcome-view');
  const taskView = $('#task-view');
  if (welcome) welcome.style.display = 'none';
  if (taskView) (taskView as HTMLElement).style.display = 'flex';

  await fetchTaskDetails(taskId);
  await loadTasksList();
}

export async function fetchTaskDetails(taskId: string): Promise<void> {
  try {
    const task = await api.getTask(taskId);

    const json = JSON.stringify(task);
    if (json === lastDetailsJson) return;
    lastDetailsJson = json;
    setState('lastRenderedStatus', task.status);

    const titleEl = $('#active-task-desc');
    if (titleEl) {
      titleEl.textContent = task.task;
      titleEl.setAttribute('title', task.task);
    }

    const statusEl = $('#active-task-status');
    if (statusEl) {
      statusEl.textContent = statusLabel(task.status);
      statusEl.className = `task-header-badge ${statusClass(task.status)}`;
    }

    const stepEl = $('#active-task-step');
    if (stepEl) stepEl.textContent = `Step: ${task.step}`;

    renderHeaderButtons(task.status, task.details);
    renderSupervision(task);
    renderStreaming(task);
    renderLogs(task.execution_log ?? []);
    renderFileTree(task.file_tree);
    renderAgentInfo(task);
    renderIntervention(task);

    const chatBar = $('#task-chat-bar');
    if (chatBar) show(chatBar, 'flex');
  } catch (err) {
    console.error('Error loading task details', err);
    deselectTask();
    closeEditor();

    const welcome = $('#welcome-view');
    const taskView = $('#task-view');
    if (welcome) show(welcome, 'flex');
    if (taskView) hide(taskView);

    const chatBar = $('#task-chat-bar');
    if (chatBar) hide(chatBar);
  }
}

function renderHeaderButtons(status: TaskStatus, details?: string): void {
  const finishBtn = $('#btn-finish-task');
  const continueBtn = $('#btn-continue-task') as HTMLButtonElement | null;
  const motivoEl = $('#task-motivo');
  const motivoText = $('#task-motivo-text');

  if (finishBtn) {
    if (status === 'completed' || status === 'failed') hide(finishBtn);
    else show(finishBtn, 'flex');
  }

  if (status === 'failed') {
    show(continueBtn, 'flex');
    if (motivoEl && details) {
      if (motivoText) motivoText.textContent = details;
      show(motivoEl, 'flex');
    } else if (motivoEl) {
      hide(motivoEl);
    }
  } else {
    hide(continueBtn);
    if (motivoEl) hide(motivoEl);
  }
}

function renderSupervision(task: {
  status: TaskStatus;
  supervision_status?: string;
  supervision_review_summary?: string;
  supervision_reason?: string;
  supervision_last_review?: string;
  errors_encountered?: string[];
}): void {
  const banner = $('#supervision-banner');
  if (!banner) return;

  const showBanner =
    (task.status === 'completed' || task.status === 'failed') &&
    task.supervision_status === 'reviewed' &&
    (task.supervision_review_summary || task.supervision_reason);

  if (!showBanner) {
    hide(banner);
    return;
  }

  const hasErrors = task.errors_encountered?.length;
  const title = $('#supervision-title');
  const status = $('#supervision-status');
  const reason = $('#supervision-reason');
  const timestamp = $('#supervision-timestamp');
  const extra = $('#supervision-extra');

  if (title) title.textContent = hasErrors ? '🛡️ Supervisor agindo após erro' : 'Supervisor Final Analysis';
  if (status) {
    status.textContent = 'REVIEWED';
    status.className = 'supervision-pill status-reviewed';
  }
  if (reason) reason.textContent = task.supervision_reason ?? 'No supervisor reasoning available.';
  if (timestamp) timestamp.textContent = task.supervision_last_review ? `Reviewed: ${formatDate(task.supervision_last_review)}` : '';
  if (extra) extra.textContent = task.supervision_review_summary ?? '';

  show(banner, 'grid');
}

export async function pollActiveTask(): Promise<void> {
  const taskId = getState('currentTaskId');
  if (!taskId) return;

  const needsPoll =
    getState('activeTaskStatus') === 'running' ||
    getState('activeTaskStatus') === 'processando' ||
    getState('activeTaskStatus') !== getState('lastRenderedStatus') ||
    !lastDetailsJson;

  if (needsPoll) {
    await fetchTaskDetails(taskId);
  }
}

function toggleSidebar(open: boolean): void {
  const sidebar = $('#sidebar');
  const overlay = $('#sidebar-overlay');
  if (!sidebar || !overlay) return;

  sidebar.classList.toggle('open', open);
  overlay.classList.toggle('active', open);
}

export async function deleteTask(): Promise<void> {
  const taskId = getState('currentTaskId');
  if (!taskId) return;
  if (!confirm('Are you sure you want to delete this task? All workspace files and logs will be permanently removed.')) return;

  try {
    await api.deleteTask(taskId);
    deselectTask();
    closeEditor();

    const welcome = $('#welcome-view');
    const taskView = $('#task-view');
    if (welcome) show(welcome, 'flex');
    if (taskView) hide(taskView);

    const chatBar = $('#task-chat-bar');
    if (chatBar) hide(chatBar);

    await loadTasksList();
    await refreshDashboard();
  } catch (err) {
    console.error('Error deleting task', err);
    alert('Failed to delete task.');
  }
}

export async function continueTask(): Promise<void> {
  const taskId = getState('currentTaskId');
  if (!taskId) return;
  if (!confirm('Are you sure you want to continue this failed task?')) return;

  const btn = $('#btn-continue-task') as HTMLButtonElement | null;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Continuing...';
  }

  try {
    await api.continueTask(taskId);
    resetTaskState();
    lastDetailsJson = '';
    await fetchTaskDetails(taskId);
    await loadTasksList();
  } catch (err) {
    console.error('Error continuing task', err);
    alert('Failed to continue task.');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Continue';
    }
  }
}

export function initTaskButtons(): void {
  $('#btn-continue-task')?.addEventListener('click', continueTask);
  $('#btn-delete-task')?.addEventListener('click', deleteTask);
}

export function resetLastDetails(): void {
  lastDetailsJson = '';
}
