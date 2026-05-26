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
  expandedLogs: Set<string>;
  renderedLogs: Set<string>;
  expandedFolders: Set<string>;
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
  expandedLogs: new Set(),
  renderedLogs: new Set(),
  expandedFolders: new Set(),
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
  state.expandedLogs.clear();
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
