import { useEffect, useState, type FormEvent } from 'react';
import { useApp } from '../context/AppContext';
import type { FileSpecV2, GenerationResult, Manifest } from '../types';
import './PipelineV2View.css';

const stageLabelsV2: Record<string, string> = {
  generating_plan: '1. Generate JSON Plan',
  extracting_manifest: '2. Extract Manifest',
  generating_files: '3. Generate Files',
  verifying: '4. Verify & Fix',
  running_tests: '5. Run Tests',
  test_failed: '5. Tests Failed (Paused)',
  completed: 'Completed',
};

const stageIconsV2: Record<string, string> = {
  generating_plan: 'fa-file-code',
  extracting_manifest: 'fa-sitemap',
  generating_files: 'fa-folder-tree',
  verifying: 'fa-check-double',
  running_tests: 'fa-flask',
  test_failed: 'fa-triangle-exclamation',
  completed: 'fa-circle-check',
};

function LiveStatusV2({ task }: { task: Record<string, unknown> | null }) {
  if (!task) return null;

  const isActive = task.status === 'running' || task.status === 'processando';
  const isFailed = task.status === 'failed';
  const isCompleted = task.status === 'completed';
  const isRetrying = isActive && ((task.stage_retries as number) ?? 0) > 0;

  if (!isActive && !isFailed && !isCompleted) return null;

  let badgeHtml = '';
  let badgeClass = '';
  if (isRetrying) {
    badgeClass = 'status-retrying';
    badgeHtml = '<i class="fa-solid fa-rotate fa-spin"></i> Retrying';
  } else if (isActive) {
    badgeClass = 'status-running';
    badgeHtml = '<i class="fa-solid fa-circle" style="color: var(--color-running);"></i> Running';
  } else if (isFailed) {
    badgeClass = 'status-failed';
    badgeHtml = '<i class="fa-solid fa-circle-xmark"></i> Failed';
  } else if (isCompleted) {
    badgeClass = 'status-completed';
    badgeHtml = '<i class="fa-solid fa-circle-check"></i> Completed';
  }

  const stage = task.stage as string;
  const stageLabel = stage ? (stageLabelsV2[stage] ?? stage) : '';
  const stageIcon = stage ? (stageIconsV2[stage] ?? 'fa-circle') : '';

  return (
    <div className="pipeline-live-status">
      <div className="pipeline-live-inner">
        <div className="pipeline-live-head">
          <span className={`pipeline-live-badge ${badgeClass}`} dangerouslySetInnerHTML={{ __html: badgeHtml }} />
          {stageLabel ? (
            <span className="pipeline-live-stage-label">
              <i className={`fa-solid ${stageIcon}`}></i> {stageLabel}
            </span>
          ) : null}
          <span className="pipeline-live-step-label">File {(task.current_file_idx as number ?? 0) + 1}</span>
        </div>
        <div className="pipeline-live-task-desc">{task.task as string}</div>
      </div>
    </div>
  );
}

function YamlPlanViewer({ manifest, planYaml }: { manifest: Manifest | null; planYaml?: string | null }) {
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [showRaw, setShowRaw] = useState(false);

  if (!manifest && !planYaml) {
    return (
      <div className="pipeline-v2-section">
        <div className="section-title">JSON Plan</div>
        <div className="pipeline-v2-empty">No plan yet</div>
      </div>
    );
  }

  const toggleFile = (path: string) => {
    setExpandedFiles(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const files = manifest?.files ?? [];

  return (
    <div className="pipeline-v2-section">
      <div className="section-title">
        JSON Plan
        {planYaml && (
          <button className="btn-toggle-raw" onClick={() => setShowRaw(!showRaw)}>
            {showRaw ? 'Tree' : 'Raw YAML'}
          </button>
        )}
      </div>

      {showRaw && planYaml ? (
        <pre className="yaml-raw">{planYaml}</pre>
      ) : (
        <>
          {manifest?.project && (
            <div className="plan-project-info">
              <span className="plan-project-name">{manifest.project.name}</span>
              <span className="plan-project-lang">{manifest.project.language}</span>
              <span className="plan-project-framework">{manifest.project.framework}</span>
              {manifest.entrypoint && (
                <span className="plan-project-entry">
                  <i className="fa-solid fa-play"></i> {manifest.entrypoint}
                </span>
              )}
            </div>
          )}

          <div className="plan-files-list">
            {files.map((f: FileSpecV2) => {
              const isExpanded = expandedFiles.has(f.path);
              return (
                <div key={f.path} className="plan-file-card">
                  <div className="plan-file-header" onClick={() => toggleFile(f.path)}>
                    <i className={`fa-solid fa-chevron-${isExpanded ? 'down' : 'right'} expand-icon`}></i>
                    <i className={`fa-solid ${fileTypeIcon(f.type)} file-type-icon`}></i>
                    <span className="plan-file-path">{f.path}</span>
                    <span className="plan-file-type-badge">{f.type}</span>
                  </div>
                  {f.description && (
                    <div className="plan-file-desc">{f.description}</div>
                  )}
                  {isExpanded && (
                    <FileSpecDetail fileSpec={f} />
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function fileTypeIcon(type: string): string {
  switch (type) {
    case 'entrypoint': return 'fa-play';
    case 'component': return 'fa-cube';
    case 'config': return 'fa-gear';
    case 'test': return 'fa-flask';
    case 'util': return 'fa-toolbox';
    case 'style': return 'fa-palette';
    case 'static': return 'fa-file';
    default: return 'fa-file-code';
  }
}

function FileSpecDetail({ fileSpec }: { fileSpec: FileSpecV2 }) {
  const imports = fileSpec.imports ?? [];
  const functions = fileSpec.functions ?? [];
  const constants = fileSpec.constants ?? [];
  const deps = fileSpec.dependencies ?? [];

  return (
    <div className="plan-file-detail">
      {deps.length > 0 && (
        <div className="detail-section">
          <span className="detail-label">Dependencies:</span>
          {deps.map(d => <span key={d} className="detail-badge dep-badge">{d}</span>)}
        </div>
      )}

      {imports.length > 0 && (
        <div className="detail-section">
          <span className="detail-label">Imports:</span>
          <div className="imports-list">
            {imports.map((imp, i) => (
              <span key={i} className={`import-badge ${imp.external ? 'external' : 'internal'}`}>
                {imp.module}
                {imp.items.length > 0 && <span className="import-items"> ({imp.items.join(', ')})</span>}
              </span>
            ))}
          </div>
        </div>
      )}

      {functions.length > 0 && (
        <div className="detail-section">
          <span className="detail-label">Functions:</span>
          <div className="functions-list">
            {functions.map((fn, i) => (
              <FunctionSpecCard key={i} fn={fn} />
            ))}
          </div>
        </div>
      )}

      {constants.length > 0 && (
        <div className="detail-section">
          <span className="detail-label">Constants:</span>
          <div className="constants-list">
            {constants.map((c, i) => (
              <span key={i} className="constant-badge">
                {c.name}: {c.type} = {c.value}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FunctionSpecCard({ fn }: { fn: { name: string; description: string; inputs: Array<{ name: string; type: string; required: boolean; description: string }>; outputs: Array<{ name: string; type: string; description: string }>; calls: string[] } }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="function-spec-card">
      <div className="function-spec-header" onClick={() => setExpanded(!expanded)}>
        <i className={`fa-solid fa-chevron-${expanded ? 'down' : 'right'} expand-icon`}></i>
        <span className="function-name">{fn.name}</span>
        <span className="function-arrow">→</span>
        <span className="function-output">{fn.outputs.length > 0 ? fn.outputs.map(o => `${o.name}: ${o.type}`).join(', ') : 'void'}</span>
      </div>
      {fn.description && <div className="function-spec-desc">{fn.description}</div>}
      {expanded && (
        <div className="function-spec-detail">
          <div className="param-section">
            <span className="param-label">Inputs:</span>
            {fn.inputs.length === 0 ? <span className="param-none">None</span> : (
              <ul className="param-list">
                {fn.inputs.map((p, i) => (
                  <li key={i} className="param-item">
                    <span className="param-name">{p.name}</span>
                    <span className="param-type">{p.type}</span>
                    {!p.required && <span className="param-optional">optional</span>}
                    {p.description && <span className="param-desc">{p.description}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="param-section">
            <span className="param-label">Outputs:</span>
            {fn.outputs.length === 0 ? <span className="param-none">None</span> : (
              <ul className="param-list">
                {fn.outputs.map((p, i) => (
                  <li key={i} className="param-item">
                    <span className="param-name">{p.name}</span>
                    <span className="param-type">{p.type}</span>
                    {p.description && <span className="param-desc">{p.description}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {fn.calls.length > 0 && (
            <div className="param-section">
              <span className="param-label">Internal calls:</span>
              {fn.calls.map(c => <span key={c} className="detail-badge call-badge">{c}</span>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FileGenerationProgress({
  generationOrder,
  filesGenerated,
  currentFileIdx,
}: {
  generationOrder: string[];
  filesGenerated: GenerationResult[];
  currentFileIdx: number;
}) {
  const total = generationOrder.length;
  const completed = filesGenerated.length;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

  const statusMap: Record<string, { success: boolean; error?: string | null }> = {};
  for (const r of filesGenerated) {
    statusMap[r.path] = { success: r.success, error: r.error };
  }

  return (
    <div className="pipeline-v2-section">
      <div className="section-title">
        File Generation
        <span className="progress-text">{completed}/{total} files ({percent}%)</span>
      </div>

      <div className="progress-bar-container">
        <div className="progress-bar" style={{ width: `${percent}%` }}></div>
      </div>

      <div className="generation-timeline">
        {generationOrder.map((path, i) => {
          const status = statusMap[path];
          let cls = 'timeline-pending';
          let icon = 'fa-circle';
          if (i < currentFileIdx && status) {
            cls = status.success ? 'timeline-success' : 'timeline-failed';
            icon = status.success ? 'fa-circle-check' : 'fa-circle-xmark';
          } else if (i === currentFileIdx) {
            cls = 'timeline-active';
            icon = 'fa-spinner fa-spin';
          }

          return (
            <div key={path} className={`timeline-item ${cls}`}>
              <div className="timeline-marker">
                <i className={`fa-solid ${icon}`}></i>
              </div>
              <div className="timeline-content">
                <span className="timeline-path">{path}</span>
                {status?.error && <span className="timeline-error">{status.error}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PipelineStageCards({ stage }: { stage: string }) {
  const stages = ['generating_plan', 'extracting_manifest', 'generating_files', 'verifying', 'running_tests'];
  const currentIdx = stages.indexOf(stage);

  return (
    <div className="pipeline-v2-section">
      <div className="section-title">Pipeline Stages</div>
      <div className="stage-cards">
        {stages.map((s, i) => {
          let cls = 'stage-card';
          if (i < currentIdx) cls += ' stage-done';
          else if (i === currentIdx) cls += ' stage-active';
          else cls += ' stage-pending';

          return (
            <div key={s} className={cls}>
              <div className="stage-card-icon">
                <i className={`fa-solid ${stageIconsV2[s] ?? 'fa-circle'}`}></i>
              </div>
              <div className="stage-card-label">{(stageLabelsV2[s] ?? s).replace(/^\d+\.\s*/, '')}</div>
              <div className="stage-card-num">{i + 1}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AgentChatInput({ taskId: _taskId }: { taskId: string }) {
  const { sendChatPrompt } = useApp();
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!message.trim() || sending) return;
    setSending(true);
    try {
      await sendChatPrompt(message.trim());
      setMessage('');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="pipeline-v2-section agent-chat-section">
      <div className="section-title">
        <i className="fa-solid fa-comment"></i>
        <span>Send Message to Agent</span>
      </div>
      <form className="agent-chat-form" onSubmit={handleSubmit}>
        <textarea
          className="agent-chat-input"
          placeholder="Ask the agent to fix errors, analyze files, or modify the task..."
          value={message}
          onChange={e => setMessage(e.target.value)}
          rows={3}
          disabled={sending}
        />
        <button
          className="btn-chat-send"
          type="submit"
          disabled={!message.trim() || sending}
        >
          {sending ? (
            <i className="fa-solid fa-spinner fa-spin"></i>
          ) : (
            <i className="fa-solid fa-paper-plane"></i>
          )}
          <span>Send</span>
        </button>
      </form>
    </div>
  );
}

export default function PipelineV2View() {
  const { currentTask, currentTaskId } = useApp();
  const [task, setTask] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (currentTask) {
      setTask(currentTask as unknown as Record<string, unknown>);
    }
  }, [currentTask]);

  if (!task && !currentTaskId) {
    return (
      <div className="pipeline-v2 empty-state">
        <div className="empty-state-icon">
          <i className="fa-solid fa-brain-circuit"></i>
        </div>
        <div className="empty-state-title">Agentic Pipeline V2</div>
        <div className="empty-state-desc">
          Create a new task to see the YAML-based structured pipeline.
        </div>
      </div>
    );
  }

  if (!task) {
    return (
      <div className="pipeline-v2 loading-state">
        <i className="fa-solid fa-spinner fa-spin"></i> Loading...
      </div>
    );
  }

  const manifest = (task.manifest as Manifest) ?? null;
  const planJson = (task.plan_json as string) ?? (task.plan_yaml as string) ?? null;
  const generationOrder = (task.generation_order as string[]) ?? [];
  const filesGenerated = (task.files_generated as GenerationResult[]) ?? [];
  const currentFileIdx = (task.current_file_idx as number) ?? 0;
  const stage = (task.stage as string) ?? '';

  return (
    <div className="pipeline-v2">
      <LiveStatusV2 task={task} />
      <PipelineStageCards stage={stage} />
      <YamlPlanViewer manifest={manifest} planYaml={planJson} />
      {generationOrder.length > 0 && (
        <FileGenerationProgress
          generationOrder={generationOrder}
          filesGenerated={filesGenerated}
          currentFileIdx={currentFileIdx}
        />
      )}
      {currentTaskId && <AgentChatInput taskId={currentTaskId} />}
    </div>
  );
}
