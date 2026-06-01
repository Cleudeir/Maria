export type TabName = 'logs' | 'streaming' | 'agent' | 'workspace';
export type EditorTab = 'code' | 'preview';
export type FinishOutcome = 'completed' | 'failed';
export type InterventionAction = 'approve' | 'modify' | 'continue';

export interface LlmUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  tokens_per_second?: number;
  prompt_tokens_per_second?: number;
  tokens?: number;
}

export interface LogEntry {
  step?: number | null;
  role: string;
  content: string;
  llm_usage?: LlmUsage;
}

export interface ProposedTool {
  name: string;
  args: Record<string, unknown>;
}

export interface FileTreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileTreeNode[];
}

export interface Task {
  task_id: string;
  task: string;
  status: TaskStatus;
  step: number;
  stage?: string;
  stage_retries?: number;
  created_at?: string;
  mode?: string;
  execution_log?: LogEntry[];
  file_tree?: FileTreeNode[];
  proposed_tool?: ProposedTool | null;
  is_streaming?: boolean;
  current_streaming_response?: string;
  current_command_output?: string;
  details?: string;
  supervision_status?: string;
  supervision_review_summary?: string;
  supervision_reason?: string;
  supervision_last_review?: string;
  errors_encountered?: string[];
}

export interface DashboardStats {
  total_tasks: number;
  success_rate: number;
  running: number;
  lessons_count: number;
}

export interface DashboardResponse {
  stats: DashboardStats;
}

export interface TaskListResponse extends Array<{
  task_id: string;
  task: string;
  status: TaskStatus;
  step: number;
  created_at?: string;
}> {}

export interface TaskDetailsResponse extends Task {}

export interface FileViewResponse {
  content: string;
  path: string;
}

export interface LessonsResponse {
  lessons: Array<{
    title: string;
    error?: string;
    resolution: string;
  }>;
}

export interface PromptResponse {
  prompt: string;
}

export interface ToolConfig {
  icon: string;
  color: string;
}

export interface HttpServerInfo {
  server_id: string;
  task_id: string;
  port: number;
  path: string;
  url: string;
  started_at: number;
  alive: boolean;
}

export interface HttpServersResponse {
  servers: HttpServerInfo[];
}

export type TaskStatus =
  | 'running'
  | 'processando'
  | 'completed'
  | 'failed'
  | 'awaiting_intervention'
  | 'legacy';
