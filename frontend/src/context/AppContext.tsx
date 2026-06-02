import { createContext, useContext, useState, useCallback, useRef, type ReactNode } from 'react';
import type { Task, TabName, EditorTab, FinishOutcome, DashboardStats } from '../types';
import { api } from '../api/client';

interface AppState {
  currentTaskId: string | null;
  activeTaskStatus: Task['status'] | null;
  currentTab: TabName;
  editorTab: EditorTab;
  editingFilePath: string | null;
  finishOutcome: FinishOutcome;
  logAutoScroll: boolean;
  expandedFolders: Set<string>;
  batchSelectionMode: boolean;
  selectedTasksForDelete: Set<string>;
  tasks: Array<{ task_id: string; task: string; status: Task['status']; step: number; created_at?: string }>;
  currentTask: Task | null;
  dashboard: DashboardStats | null;
  lastTasksJson: string;
  lastDetailsJson: string;
}

interface AppContextValue extends AppState {
  selectTask: (taskId: string) => void;
  deselectTask: () => void;
  setCurrentTab: (tab: TabName) => void;
  setEditorTab: (tab: EditorTab) => void;
  setEditingFilePath: (path: string | null) => void;
  setFinishOutcome: (outcome: FinishOutcome) => void;
  setLogAutoScroll: (v: boolean) => void;
  toggleBatchSelectionMode: () => void;
  toggleTaskSelection: (taskId: string) => void;
  clearSelectedTasks: () => void;
  refreshDashboard: () => Promise<void>;
  loadTasksList: () => Promise<void>;
  fetchTaskDetails: (taskId: string) => Promise<void>;
  selectTaskById: (taskId: string) => Promise<void>;
  stopTask: () => Promise<void>;
  continueTask: () => Promise<void>;
  deleteTask: () => Promise<void>;
  batchDeleteTasks: () => Promise<void>;
  sendChatPrompt: (prompt: string) => Promise<void>;
  closeEditor: () => void;
}

const defaultDashboard: DashboardStats = { total_tasks: 0, success_rate: 0, running: 0, lessons_count: 0 };

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [activeTaskStatus, setActiveTaskStatus] = useState<Task['status'] | null>(null);
  const [currentTab, setCurrentTab] = useState<TabName>('logs');
  const [editorTab, setEditorTab] = useState<EditorTab>('code');
  const [editingFilePath, setEditingFilePath] = useState<string | null>(null);
  const [finishOutcome, setFinishOutcome] = useState<FinishOutcome>('completed');
  const [logAutoScroll, setLogAutoScroll] = useState(true);
  const [expandedFolders] = useState<Set<string>>(new Set());
  const [batchSelectionMode, setBatchSelectionMode] = useState(false);
  const [selectedTasksForDelete] = useState<Set<string>>(new Set());
  const [tasks, setTasks] = useState<AppState['tasks']>([]);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [dashboard, setDashboard] = useState<DashboardStats | null>(null);
  const lastTasksJsonRef = useRef('');
  const lastDetailsJsonRef = useRef('');

  const clearTaskState = useCallback(() => {
    setEditingFilePath(null);
    setEditorTab('code');
  }, []);

  const selectTask = useCallback((taskId: string) => {
    setCurrentTaskId(taskId);
    clearTaskState();
  }, [clearTaskState]);

  const deselectTask = useCallback(() => {
    setCurrentTaskId(null);
    setActiveTaskStatus(null);
    clearTaskState();
  }, [clearTaskState]);

  const toggleBatchSelectionModeFn = useCallback(() => {
    setBatchSelectionMode(prev => {
      if (prev) selectedTasksForDelete.clear();
      return !prev;
    });
  }, [selectedTasksForDelete]);

  const toggleTaskSelection = useCallback((taskId: string) => {
    if (selectedTasksForDelete.has(taskId)) {
      selectedTasksForDelete.delete(taskId);
    } else {
      selectedTasksForDelete.add(taskId);
    }
  }, [selectedTasksForDelete]);

  const clearSelectedTasksFn = useCallback(() => {
    selectedTasksForDelete.clear();
  }, [selectedTasksForDelete]);

  const refreshDashboard = useCallback(async () => {
    try {
      const data = await api.dashboard();
      setDashboard(data.stats);
    } catch {}
  }, []);

  const loadTasksList = useCallback(async () => {
    try {
      const list = await api.listTasks();
      const active = list.find(t => t.task_id === currentTaskIdRef.current);
      const newStatus = active?.status ?? null;
      setActiveTaskStatus(prev => {
        if (prev === newStatus) return prev;
        return newStatus;
      });
      const json = `${currentTaskId}|${JSON.stringify(list)}`;
      if (json === lastTasksJsonRef.current) return;
      lastTasksJsonRef.current = json;
      setTasks(list);
    } catch {}
  }, [currentTaskId]);

  const currentTaskIdRef = useRef(currentTaskId);
  currentTaskIdRef.current = currentTaskId;

  const fetchTaskDetails = useCallback(async (taskId: string) => {
    try {
      const task = await api.getTask(taskId);
      const json = JSON.stringify(task);
      if (json === lastDetailsJsonRef.current) return;
      lastDetailsJsonRef.current = json;
      setCurrentTask(task);
    } catch {
      deselectTask();
    }
  }, [deselectTask]);

  const selectTaskById = useCallback(async (taskId: string) => {
    if (currentTaskId === taskId) return;
    selectTask(taskId);
    setCurrentTab('logs');
    await fetchTaskDetails(taskId);
    await loadTasksList();
  }, [currentTaskId, selectTask, fetchTaskDetails, loadTasksList]);

  const stopTask = useCallback(async () => {
    if (!currentTaskId) return;
    try {
      await api.stopTask(currentTaskId);
      lastDetailsJsonRef.current = '';
      await fetchTaskDetails(currentTaskId);
      await loadTasksList();
    } catch {}
  }, [currentTaskId, fetchTaskDetails, loadTasksList]);

  const continueTask = useCallback(async () => {
    if (!currentTaskId) return;
    try {
      await api.continueTask(currentTaskId);
      lastDetailsJsonRef.current = '';
      await fetchTaskDetails(currentTaskId);
      await loadTasksList();
    } catch {}
  }, [currentTaskId, fetchTaskDetails, loadTasksList]);

  const deleteTaskFn = useCallback(async () => {
    if (!currentTaskId) return;
    try {
      await api.deleteTask(currentTaskId);
      deselectTask();
      await loadTasksList();
      await refreshDashboard();
    } catch {}
  }, [currentTaskId, deselectTask, loadTasksList, refreshDashboard]);

  const batchDeleteTasks = useCallback(async () => {
    const tasksToDelete = Array.from(selectedTasksForDelete);
    if (tasksToDelete.length === 0) return;
    for (const taskId of tasksToDelete) {
      try { await api.deleteTask(taskId); } catch {}
    }
    clearSelectedTasksFn();
    toggleBatchSelectionModeFn();
    if (currentTaskId && selectedTasksForDelete.has(currentTaskId)) {
      deselectTask();
    }
    await loadTasksList();
    await refreshDashboard();
  }, [selectedTasksForDelete, currentTaskId, clearSelectedTasksFn, toggleBatchSelectionModeFn, deselectTask, loadTasksList, refreshDashboard]);

  const closeEditor = useCallback(() => {
    setEditingFilePath(null);
    setEditorTab('code');
  }, []);

  const sendChatPrompt = useCallback(async (prompt: string) => {
    if (!currentTaskId || !prompt) return;
    try {
      await api.taskAction(currentTaskId, { action: 'inject', user_prompt: prompt });
      lastDetailsJsonRef.current = '';
      await fetchTaskDetails(currentTaskId);
      await loadTasksList();
    } catch {}
  }, [currentTaskId, fetchTaskDetails, loadTasksList]);

  return (
    <AppContext.Provider value={{
      currentTaskId, activeTaskStatus, currentTab, editorTab,
      editingFilePath, finishOutcome, logAutoScroll,
      expandedFolders, batchSelectionMode, selectedTasksForDelete,
      tasks, currentTask, dashboard,
      lastTasksJson: lastTasksJsonRef.current,
      lastDetailsJson: lastDetailsJsonRef.current,
      selectTask, deselectTask, setCurrentTab, setEditorTab,
      setEditingFilePath, setFinishOutcome, setLogAutoScroll,
      toggleBatchSelectionMode: toggleBatchSelectionModeFn,
      toggleTaskSelection, clearSelectedTasks: clearSelectedTasksFn,
      refreshDashboard, loadTasksList, fetchTaskDetails,
      selectTaskById, stopTask, continueTask,
      deleteTask: deleteTaskFn, batchDeleteTasks,
      sendChatPrompt, closeEditor,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
