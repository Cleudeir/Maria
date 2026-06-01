import type { Task, TabName, EditorTab, FinishOutcome } from '../types';

interface AppState {
  currentTaskId: string | null;
  activeTaskStatus: Task['status'] | null;
  lastRenderedStatus: Task['status'] | null;
  currentTab: TabName;
  editorTab: EditorTab;
  editingFilePath: string | null;
  finishOutcome: FinishOutcome;
  logAutoScroll: boolean;
  renderedLogs: Set<string>;
  expandedFolders: Set<string>;
  batchSelectionMode: boolean;
  selectedTasksForDelete: Set<string>;
}

const state: AppState = {
  currentTaskId: null,
  activeTaskStatus: null,
  lastRenderedStatus: null,
  currentTab: 'logs',
  editorTab: 'code',
  editingFilePath: null,
  finishOutcome: 'completed',
  logAutoScroll: true,
  renderedLogs: new Set(),
  expandedFolders: new Set(),
  batchSelectionMode: false,
  selectedTasksForDelete: new Set(),
};

export function getState<K extends keyof AppState>(key: K): AppState[K] {
  return state[key];
}

export function setState<K extends keyof AppState>(
  key: K,
  value: AppState[K],
): void {
  state[key] = value;
}

export function resetTaskState(): void {
  state.renderedLogs.clear();
  state.expandedFolders.clear();
  state.editingFilePath = null;
  state.editorTab = 'code';
}

export function selectTask(taskId: string): void {
  state.currentTaskId = taskId;
  resetTaskState();
}

export function deselectTask(): void {
  state.currentTaskId = null;
  state.activeTaskStatus = null;
  state.lastRenderedStatus = null;
  resetTaskState();
}

export function toggleBatchSelectionMode(): void {
  state.batchSelectionMode = !state.batchSelectionMode;
  if (!state.batchSelectionMode) {
    state.selectedTasksForDelete.clear();
  }
}

export function toggleTaskSelection(taskId: string): void {
  if (state.selectedTasksForDelete.has(taskId)) {
    state.selectedTasksForDelete.delete(taskId);
  } else {
    state.selectedTasksForDelete.add(taskId);
  }
}

export function clearSelectedTasks(): void {
  state.selectedTasksForDelete.clear();
}

export function getSelectedTasks(): Set<string> {
  return state.selectedTasksForDelete;
}
