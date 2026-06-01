import Navigo from 'navigo';
import { deselectTask } from '../state/store';
import { $, hide, show } from '../utils/dom';
import { resetPipelineRender, renderPipeline } from './pipeline';
import { closeEditor } from './editor';

let router: Navigo;

function setHeaderActive(view: 'pipeline' | 'tasks'): void {
  const pipelineLink = $('#header-link-pipeline');
  const tasksLink = $('#header-link-tasks');
  if (pipelineLink) pipelineLink.classList.toggle('active', view === 'pipeline');
  if (tasksLink) tasksLink.classList.toggle('active', view === 'tasks');
}

function hideSidebar(): void {
  hide($('#sidebar'));
  hide($('#sidebar-overlay'));
}

function showSidebar(): void {
  show($('#sidebar'));
}

export function navigateHome(): void {
  router.navigate('/task');
}

export function navigateToPipeline(): void {
  router.navigate('/pipeline');
}

export function navigateToTask(taskId: string): void {
  router.navigate(`/task/${taskId}`);
}

export function initRouter(): void {
  router = new Navigo('/', { hash: false });

  router.on({
    '/': () => {
      showPipeline();
    },
    '/pipeline': () => {
      showPipeline();
    },
    '/task': () => {
      showTasks();
    },
    '/task/:id': (params: { data: { id: string } }) => {
      const taskId = params?.data?.id;
      if (taskId) {
        import('../handlers/tasks').then(({ selectTaskById }) => {
          selectTaskById(taskId);
        });
        showTaskView();
      }
    },
  });

  router.resolve();
  router.updatePageLinks();
}

function showPipeline(): void {
  deselectTask();
  closeEditor();
  hideSidebar();

  hide($('#home-view'));
  hide($('#task-view'));
  show($('#pipeline-view'), 'flex');

  setHeaderActive('pipeline');
  resetPipelineRender();
  renderPipeline('pipeline-view-container');
}

function showTasks(): void {
  deselectTask();
  closeEditor();
  showSidebar();

  hide($('#home-view'));
  hide($('#pipeline-view'));
  hide($('#task-view'));
  show($('#home-view'), 'flex');

  setHeaderActive('tasks');
}

function showTaskView(): void {
  showSidebar();

  hide($('#home-view'));
  hide($('#pipeline-view'));
  show($('#task-view'), 'flex');

  setHeaderActive('tasks');
}
