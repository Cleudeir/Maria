import { loadTasksList, refreshDashboard, pollActiveTask, initTaskButtons } from './handlers/tasks';
import { initTabs } from './ui/tabs';
import { initLogScroll } from './ui/logs';
import { initEditor } from './ui/editor';
import { initIntervention } from './handlers/interventions';
import { initModals } from './handlers/modals';
import { getState } from './state/store';

function init(): void {
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
