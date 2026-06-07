export type TabName = 'logs' | 'streaming' | 'created' | 'agent' | 'workspace';
export type EditorTab = 'code' | 'preview';
export type FinishOutcome = 'completed' | 'failed';

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

export interface FileTreeNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileTreeNode[];
}

export interface CreatedFile {
  path: string;
  created_at: string;
  step?: number;
}

export interface ToCreateFile {
  path: string;
}

export interface YamlProject {
  name: string;
  description: string;
  language: string;
  framework: string;
}

export interface ParameterSpec {
  name: string;
  type: string;
  required: boolean;
  default?: unknown;
  description: string;
}

export interface FunctionSpecV2 {
  name: string;
  description: string;
  inputs: ParameterSpec[];
  outputs: ParameterSpec[];
  calls: string[];
}

export interface ImportSpecV2 {
  module: string;
  items: string[];
  external: boolean;
}

export interface ConstantSpecV2 {
  name: string;
  type: string;
  value: string;
  description: string;
}

export interface FileSpecV2 {
  path: string;
  description: string;
  type: 'module' | 'component' | 'config' | 'test' | 'util' | 'entrypoint' | 'style' | 'static';
  imports: ImportSpecV2[];
  functions: FunctionSpecV2[];
  constants: ConstantSpecV2[];
  dependencies: string[];
}

export interface Manifest {
  project: YamlProject;
  files: FileSpecV2[];
  entrypoint: string;
}

export interface GenerationResult {
  path: string;
  success: boolean;
  error: string | null;
  content: string | null;
  functions_generated: string[];
  warning?: string;
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
  is_streaming?: boolean;
  current_streaming_response?: string;
  current_command_output?: string;
  details?: string;
  supervision_status?: string;
  supervision_review_summary?: string;
  supervision_reason?: string;
  supervision_last_review?: string;
  errors_encountered?: string[];
  created_files?: CreatedFile[];
  project_files_to_create?: ToCreateFile[];
  files_progress?: number;
  plan_yaml?: string | null;
  plan_json?: string | null;
  manifest?: Manifest | null;
  generation_order?: string[];
  current_file_idx?: number;
  files_generated?: GenerationResult[];
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
  | 'legacy';
