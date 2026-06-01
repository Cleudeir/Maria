import { loadTasksList, refreshDashboard, pollActiveTask, initTaskButtons, renderActiveServers } from './handlers/tasks';
import { initTabs } from './ui/tabs';
import { initLogScroll } from './ui/logs';
import { initEditor } from './ui/editor';
import { initIntervention } from './handlers/interventions';
import { initModals } from './handlers/modals';
import { renderPipeline, resetPipelineRender, updatePipelineTaskStatus } from './ui/pipeline';
import { initRouter, navigateToPipeline } from './ui/router';
import { initOpenFolderButton } from './ui/filetree';
import { getState } from './state/store';
import { api } from './api/client';
import { $ } from './utils/dom';

function initTheme(): void {
  const saved = localStorage.getItem('maria-theme') ?? 'light';
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeButton(saved);

  $('#btn-theme-toggle')?.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('maria-theme', next);
    updateThemeButton(next);
    resetPipelineRender();
    renderPipeline('pipeline-view-container');
  });
}

function updateThemeButton(theme: string): void {
  const btn = $('#btn-theme-toggle');
  if (!btn) return;
  if (theme === 'dark') {
    btn.innerHTML = '<i class="fa-solid fa-sun"></i> Light Mode';
  } else {
    btn.innerHTML = '<i class="fa-solid fa-moon"></i> Dark Mode';
  }
}

function init(): void {
  initTheme();
  refreshDashboard();
  loadTasksList();

  initTabs();
  initLogScroll();
  initEditor();
  initIntervention();
  initModals();
  initTaskButtons();
  initRouter();
  initOpenFolderButton();

  $('#btn-pipeline-page')?.addEventListener('click', navigateToPipeline);

  setInterval(async () => {
    await loadTasksList();
    if (getState('currentTaskId')) {
      await pollActiveTask();
      const currentId = getState('currentTaskId');
      if (currentId) {
        try { await renderActiveServers(currentId); } catch {}
      }
    } else {
      await refreshDashboard();
      const pipelineView = $('#pipeline-view');
      if (pipelineView && pipelineView.style.display !== 'none') {
        try {
          const tasks = await api.listTasks();
          const relevant = tasks.find(t =>
            t.status === 'running' || t.status === 'processando' || t.status === 'awaiting_intervention'
          ) || tasks.find(t => t.status === 'failed') || tasks[tasks.length - 1];
          if (relevant) {
            const details = await api.getTask(relevant.task_id);
            updatePipelineTaskStatus(details as any);
          }
        } catch {}
      }
    }
  }, 1200);
}

document.addEventListener('DOMContentLoaded', init);
