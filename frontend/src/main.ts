import { loadTasksList, refreshDashboard, pollActiveTask, initTaskButtons } from './handlers/tasks';
import { initTabs } from './ui/tabs';
import { initLogScroll } from './ui/logs';
import { initEditor } from './ui/editor';
import { initIntervention } from './handlers/interventions';
import { initModals } from './handlers/modals';
import { getState } from './state/store';
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

  setInterval(() => {
    loadTasksList();
    if (getState('currentTaskId')) {
      pollActiveTask();
    } else {
      refreshDashboard();
    }
  }, 1200);
}

document.addEventListener('DOMContentLoaded', init);
