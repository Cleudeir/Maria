import type { HttpServerInfo, TaskStatus } from '../types';
import { getState, setState, selectTask, resetTaskState, toggleBatchSelectionMode, toggleTaskSelection, clearSelectedTasks, getSelectedTasks } from '../state/store';
import { $, hide, show } from '../utils/dom';
import { escapeHtml, formatDate } from '../utils/formatters';
import { api } from '../api/client';
import { renderLogs } from '../ui/logs';
import { renderStreaming } from '../ui/streaming';
import { renderAgentInfo, renderIntervention } from '../ui/agent';
import { renderFileTree } from '../ui/filetree';
import { closeEditor } from '../ui/editor';
import { navigateToTask, navigateHome } from '../ui/router';
import { updatePipelineTaskStatus } from '../ui/pipeline';

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

    const batchMode = getState('batchSelectionMode');
    const selectedTasks = getSelectedTasks();

    for (const task of tasks) {
      const isActive = task.task_id === getState('currentTaskId');
      const isSelected = selectedTasks.has(task.task_id);
      const item = document.createElement('div');
      item.className = `task-item${isActive ? ' active' : ''}${isSelected ? ' selected' : ''}`;
      item.dataset.taskId = task.task_id;

      if (batchMode) {
        item.innerHTML = `
          <div class="task-item-checkbox">
            <input type="checkbox" ${isSelected ? 'checked' : ''} data-task-id="${task.task_id}" />
          </div>
          <div class="task-item-content">
            <div class="task-item-header">
              <span class="task-item-id">${task.task_id}</span>
              <span class="task-item-status ${statusClass(task.status)}">${statusLabel(task.status)}</span>
            </div>
            <div class="task-item-desc" title="${task.task}">${task.task}</div>
            <div class="task-item-date">
              <span>Step: ${task.step}</span>
              <span>${task.created_at ?? ''}</span>
            </div>
          </div>
        `;
        const checkbox = item.querySelector('input[type="checkbox"]');
        checkbox?.addEventListener('click', (e) => {
          e.stopPropagation();
          toggleTaskSelection(task.task_id);
          item.classList.toggle('selected');
          updateSelectedCount();
        });
        item.addEventListener('click', () => {
          (checkbox as HTMLInputElement | null)?.click();
        });
      } else {
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
      }
      list.appendChild(item);
    }

    updateBatchActionsVisibility();
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

export async function selectTaskById(taskId: string): Promise<void> {
  if (getState('currentTaskId') === taskId) return;

  selectTask(taskId);
  closeEditor();
  toggleSidebar(false);
  navigateToTask(taskId);

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
    renderLogs(task.execution_log ?? [], task.current_command_output);
    renderFileTree(task.file_tree);
    renderAgentInfo(task);
    renderIntervention(task);
    void renderActiveServers(task.task_id);

    const chatBar = $('#task-chat-bar');
    if (chatBar) show(chatBar, 'flex');

    updatePipelineTaskStatus(task);
  } catch (err) {
    console.error('Error loading task details', err);
    navigateHome();
  }
}

function renderHeaderButtons(status: TaskStatus, details?: string): void {
  const finishBtn = $('#btn-finish-task');
  const continueBtn = $('#btn-continue-task') as HTMLButtonElement | null;
  const previewBtn = $('#btn-preview-html') as HTMLButtonElement | null;
  const motivoEl = $('#task-motivo');
  const motivoText = $('#task-motivo-text');

  if (finishBtn) {
    if (status === 'completed' || status === 'failed') hide(finishBtn);
    else show(finishBtn, 'flex');
  }

  if (status === 'completed') {
    checkAndShowPreviewButton();
  } else {
    if (previewBtn) hide(previewBtn);
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

async function checkAndShowPreviewButton(): Promise<void> {
  const taskId = getState('currentTaskId');
  const previewBtn = $('#btn-preview-html') as HTMLButtonElement | null;
  if (!taskId || !previewBtn) return;

  try {
    const { html_files } = await api.getHtmlFiles(taskId);
    if (html_files && html_files.length > 0) {
      previewBtn.onclick = () => openHtmlPreview(taskId, html_files);
      show(previewBtn, 'flex');
    } else {
      hide(previewBtn);
    }
  } catch (err) {
    console.error('Error checking HTML files', err);
    hide(previewBtn);
  }
}

function openHtmlPreview(taskId: string, htmlFiles: string[]): void {
  if (htmlFiles.length === 1) {
    window.open(`/api/tasks/${taskId}/preview/${htmlFiles[0]}`, '_blank');
  } else {
    const file = prompt(
      `Multiple HTML files found. Enter file number to preview:\n${htmlFiles.map((f, i) => `${i + 1}. ${f}`).join('\n')}\n\nFile number:`,
    );
    if (file) {
      const idx = parseInt(file, 10) - 1;
      if (idx >= 0 && idx < htmlFiles.length) {
        window.open(`/api/tasks/${taskId}/preview/${htmlFiles[idx]}`, '_blank');
      }
    }
  }
}

export async function renderActiveServers(taskId: string): Promise<void> {
  const card = $('#task-servers-card');
  const list = $('#task-servers-list');
  const testBtn = $('#btn-test-server') as HTMLButtonElement | null;
  if (!card || !list || !testBtn) return;

  let servers: HttpServerInfo[] = [];
  try {
    const res = await api.listServers();
    servers = (res.servers ?? []).filter(s => s.task_id === taskId);
  } catch (err) {
    console.error('Error listing HTTP servers', err);
  }

  if (servers.length === 0) {
    hide(card);
    hide(testBtn);
    return;
  }

  show(card, 'flex');
  show(testBtn, 'flex');

  testBtn.onclick = () => {
    if (servers.length === 1) {
      window.open(servers[0].url, '_blank');
    } else {
      const choice = prompt(
        `Multiple test servers are running. Enter number to open:\n${servers.map((s, i) => `${i + 1}. ${s.url} (${s.path})`).join('\n')}\n\nNumber:`,
      );
      if (choice) {
        const idx = parseInt(choice, 10) - 1;
        if (idx >= 0 && idx < servers.length) {
          window.open(servers[idx].url, '_blank');
        }
      }
    }
  };

  list.innerHTML = servers
    .map(s => {
      return `
        <div class="task-server-row" data-server-id="${escapeHtml(s.server_id)}">
          <a class="task-server-url" href="${escapeHtml(s.url)}" target="_blank" rel="noreferrer">
            <i class="fa-solid fa-up-right-from-square"></i>
            ${escapeHtml(s.url)}
          </a>
          <span class="task-server-path" title="${escapeHtml(s.path)}">${escapeHtml(s.path)}</span>
          <button class="btn-server-stop" data-server-id="${escapeHtml(s.server_id)}" title="Stop this server">
            <i class="fa-solid fa-stop"></i>
          </button>
        </div>
      `;
    })
    .join('');

  list.querySelectorAll<HTMLButtonElement>('.btn-server-stop').forEach(btn => {
    btn.addEventListener('click', async ev => {
      ev.preventDefault();
      const sid = btn.dataset.serverId;
      if (!sid) return;
      if (!confirm(`Stop test server ${sid}?`)) return;
      try {
        await api.stopServer(sid, taskId);
        await renderActiveServers(taskId);
      } catch (err) {
        console.error('Error stopping HTTP server', err);
        alert('Failed to stop the HTTP server.');
      }
    });
  });
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
    navigateHome();

    await loadTasksList();
    await refreshDashboard();
  } catch (err) {
    console.error('Error deleting task', err);
    alert('Failed to delete task.');
  }
}

export async function batchDeleteTasks(): Promise<void> {
  const selectedTasks = getSelectedTasks();
  if (selectedTasks.size === 0) return;
  if (!confirm(`Are you sure you want to delete ${selectedTasks.size} task(s)? All workspace files and logs will be permanently removed.`)) return;

  const tasksToDelete = Array.from(selectedTasks);
  let successCount = 0;
  let failCount = 0;

  for (const taskId of tasksToDelete) {
    try {
      await api.deleteTask(taskId);
      successCount++;
    } catch (err) {
      console.error(`Error deleting task ${taskId}`, err);
      failCount++;
    }
  }

  clearSelectedTasks();
  toggleBatchSelectionMode();

  if (getState('currentTaskId') && selectedTasks.has(getState('currentTaskId')!)) {
    navigateHome();
  }

  await loadTasksList();
  await refreshDashboard();

  if (failCount > 0) {
    alert(`Deleted ${successCount} task(s) successfully. Failed to delete ${failCount} task(s).`);
  }
}

function toggleBatchMode(): void {
  toggleBatchSelectionMode();
  clearSelectedTasks();
  loadTasksList();
}

function updateSelectedCount(): void {
  const countEl = $('#selected-count');
  if (countEl) {
    countEl.textContent = String(getSelectedTasks().size);
  }
}

function updateBatchActionsVisibility(): void {
  const batchActions = $('#batch-actions');
  if (batchActions) {
    if (getState('batchSelectionMode')) {
      show(batchActions, 'flex');
    } else {
      hide(batchActions);
    }
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
  $('#btn-batch-toggle')?.addEventListener('click', toggleBatchMode);
  $('#btn-batch-delete')?.addEventListener('click', batchDeleteTasks);
}

export function resetLastDetails(): void {
  lastDetailsJson = '';
}
