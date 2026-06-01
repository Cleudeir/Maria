import type {
  DashboardResponse,
  TaskListResponse,
  TaskDetailsResponse,
  FileViewResponse,
  LessonsResponse,
  PromptResponse,
  HttpServersResponse,
} from '../types';

const API_BASE = '';

async function request<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(error.error || `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  dashboard: () => request<DashboardResponse>('/api/dashboard'),

  listTasks: () => request<TaskListResponse>('/api/tasks'),

  getTask: (id: string) => request<TaskDetailsResponse>(`/api/tasks/${id}`),

  createTask: (data: {
    task: string;
    mode: string;
    provider_type: string;
    complexity: string;
  }) =>
    request<TaskDetailsResponse>('/api/tasks', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  taskAction: (id: string, data: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/tasks/${id}/action`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  pauseTask: (id: string) =>
    request<Record<string, unknown>>(`/api/tasks/${id}/pause`, {
      method: 'POST',
    }),

  continueTask: (id: string) =>
    request<Record<string, unknown>>(`/api/tasks/${id}/continue`, {
      method: 'POST',
    }),

  deleteTask: (id: string) =>
    request<Record<string, unknown>>(`/api/tasks/${id}`, {
      method: 'DELETE',
    }),

  viewFile: (taskId: string, path: string) =>
    request<FileViewResponse>(
      `/api/tasks/${taskId}/files/view?path=${encodeURIComponent(path)}`,
    ),

  editFile: (taskId: string, path: string, content: string) =>
    request<Record<string, unknown>>(`/api/tasks/${taskId}/files/edit`, {
      method: 'POST',
      body: JSON.stringify({ path, content }),
    }),

  rawFile: (taskId: string, path: string) =>
    `/api/tasks/${taskId}/files/raw/${path}`,

  getPrompt: () => request<PromptResponse>('/api/memory/prompt'),

  savePrompt: (prompt: string) =>
    request<Record<string, unknown>>('/api/memory/prompt', {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }),

  getLessons: () => request<LessonsResponse>('/api/memory/lessons'),

  getHtmlFiles: (taskId: string) =>
    request<{ html_files: string[] }>(`/api/tasks/${taskId}/html-files`),

  listServers: () => request<HttpServersResponse>('/api/servers'),

  stopServer: (serverId: string, taskId?: string) =>
    request<Record<string, unknown>>('/api/servers', {
      method: 'POST',
      body: JSON.stringify({ server_id: serverId, task_id: taskId }),
    }),
};
