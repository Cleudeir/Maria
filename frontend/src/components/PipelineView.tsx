import { useEffect, useRef, useState } from 'react';
import { useApp } from '../context/AppContext';
import { api } from '../api/client';

const stageLabels: Record<string, string> = {
  initializing: '0. Validação & Inicialização',
  generating_plan: '1. Generate Plan',
  generating_structure: '2. Generate Structure',
  regenerating_plan: '3. Regenerate Plan with Paths',
  creating_steps: '4. Create Steps',
  analyzing_parallelism: 'Parallelism Analysis',
  executing_steps: '5. Execute Steps',
};

const stageIcons: Record<string, string> = {
  initializing: 'fa-check-double',
  generating_plan: 'fa-layer-group',
  generating_structure: 'fa-folder-tree',
  regenerating_plan: 'fa-path',
  creating_steps: 'fa-list-tree',
  analyzing_parallelism: 'fa-diagram-project',
  executing_steps: 'fa-rotate',
};

const stageCardIdx: Record<string, number> = {
  initializing: 0,
  generating_plan: 1,
  generating_structure: 2,
  regenerating_plan: 3,
  creating_steps: 4,
  executing_steps: 5,
};

interface LiveStatusProps {
  task: {
    task_id: string;
    task: string;
    status: string;
    step?: number;
    stage?: string;
    stage_retries?: number;
    details?: string;
  } | null;
}

function LiveStatus({ task }: LiveStatusProps) {
  if (!task) return null;

  const isActive = task.status === 'running' || task.status === 'processando';
  const isFailed = task.status === 'failed';
  const isCompleted = task.status === 'completed';
  const isRetrying = isActive && (task.stage_retries ?? 0) > 0;

  if (!isActive && !isFailed && !isCompleted) return null;

  let badgeHtml = '';
  let badgeClass = '';
  if (isRetrying) {
    badgeClass = 'status-retrying';
    badgeHtml = '<i class="fa-solid fa-rotate fa-spin"></i> Retrying';
  } else if (isActive) {
    badgeClass = 'status-running';
    badgeHtml = `<i class="fa-solid fa-circle" style="color: var(--color-running);"></i> Running`;
  } else if (isFailed) {
    badgeClass = 'status-failed';
    badgeHtml = '<i class="fa-solid fa-circle-xmark"></i> Failed';
  } else if (isCompleted) {
    badgeClass = 'status-completed';
    badgeHtml = '<i class="fa-solid fa-circle-check"></i> Completed';
  }

  const stageLabel = task.stage ? (stageLabels[task.stage] ?? task.stage) : '';
  const stageIcon = task.stage ? (stageIcons[task.stage] ?? 'fa-circle') : '';

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
          <span className="pipeline-live-step-label">Step {task.step ?? 0}</span>
        </div>
        <div className="pipeline-live-task-desc">{task.task}</div>
      </div>
    </div>
  );
}

function TaskCompletionReview({ task }: { task: any }) {
  if (!task || !task.project_files_to_create) return null;
  const planned = task.project_files_to_create ?? [];
  const created = task.created_files ?? [];
  const createdSet = new Set(created.map((f: any) => f.path ?? f));
  const missing = planned.filter((f: any) => !createdSet.has(f.path ?? f));
  const hasMissing = task.status === 'completed' && missing.length > 0;

  const [busy, setBusy] = useState(false);

  if (!hasMissing) return null;

  const handleContinue = async () => {
    setBusy(true);
    const fileList = missing.map((f: any) => f.path).join('\n');
    const prompt = `CONTINUAR: Os seguintes arquivos planejados não foram criados:\n${fileList}\n\nCrie cada um dos arquivos faltantes.`;
    await api.taskAction(task.task_id, { action: 'inject', user_prompt: prompt });
    setBusy(false);
  };

  const handleFinish = async () => {
    setBusy(true);
    const fileList = missing.map((f: any) => f.path).join(', ');
    await api.taskAction(task.task_id, {
      action: 'force_complete',
      status: 'completed',
      reason: `Aceito com ${missing.length} arquivo(s) pendente(s): ${fileList}`,
    });
    setBusy(false);
  };

  return (
    <div className="pipeline-review" id="task-completion-review">
      <div className="pipeline-review-header">
        <i className="fa-solid fa-clipboard-list"></i>
        <span>Revisão de Conclusão: {missing.length} arquivo(s) pendente(s)</span>
      </div>
      <div className="pipeline-review-files">
        {planned.map((f: any) => {
          const path = f.path ?? f;
          const isCreated = createdSet.has(path);
          return (
            <div key={path} className={`pipeline-review-file ${isCreated ? 'created' : 'missing'}`}>
              <i className={`fa-solid ${isCreated ? 'fa-check-circle' : 'fa-circle-exclamation'}`}></i>
              <span className="pipeline-review-path">{path}</span>
              <span className="pipeline-review-badge">{isCreated ? 'Criado' : 'Pendente'}</span>
            </div>
          );
        })}
      </div>
      <div className="pipeline-review-actions">
        <button className="btn-action" onClick={handleContinue} disabled={busy}>
          <i className="fa-solid fa-play"></i> Continuar (criar faltantes)
        </button>
        <button className="btn-action btn-stop" onClick={handleFinish} disabled={busy}>
          <i className="fa-solid fa-check"></i> Finalizar como está
        </button>
      </div>
    </div>
  );
}

export default function PipelineView() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [liveTask, setLiveTask] = useState<any>(null);
  const initializedRef = useRef(false);
  const { deselectTask } = useApp();

  useEffect(() => {
    deselectTask();
    initializedRef.current = false;
    renderMermaid();
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current.querySelector('.mermaid');
    if (!el) return;
    try {
      (window as any).mermaid?.run({ nodes: [el] });
    } catch {}
  }, []);

  const renderMermaid = () => {
    setTimeout(async () => {
      try {
        const tasks = await api.listTasks();
        const relevant = tasks.find(t =>
          t.status === 'running' || t.status === 'processando'
        ) || tasks.find(t => t.status === 'failed') || tasks[tasks.length - 1];
        if (relevant) {
          const details = await api.getTask(relevant.task_id);
          setLiveTask(details);
        }
      } catch {}
    }, 100);
  };

  return (
    <div className="pipeline-view" id="pipeline-view">
      <div className="pipeline-view-content" id="pipeline-view-container" ref={containerRef}>
        <LiveStatus task={liveTask} />
        <TaskCompletionReview task={liveTask} />
        <div className="pipeline-diagram-wrapper">
          <div className="mermaid">{mermaidCode}</div>
        </div>
        <div className="pipeline-header">
          <div className="pipeline-header-title">
            <i className="fa-solid fa-sitemap"></i> Nova Abordagem do Pipeline
          </div>
          <div className="pipeline-header-subtitle">
            Arquitetura moderna com orquestração inteligente, execução paralela, checkpointing automático,
            e aprendizado contínuo através de self-improvement.
          </div>
        </div>
        <div className="pipeline-section-title"><i className="fa-solid fa-list-ol"></i> Estágios do Pipeline</div>
        <div className="pipeline-stages">{stages.map(renderStageCard)}</div>
        <div className="pipeline-section-title"><i className="fa-solid fa-cubes"></i> Componentes do Sistema</div>
        <div className="pipeline-info-cards">{infoCards.map(renderInfoCard)}</div>
        <div className="pipeline-section-title"><i className="fa-solid fa-arrow-right-arrow-left"></i> Fluxo Completo da Aplicação</div>
        <div className="pipeline-flow">{flowSteps.map(renderFlowCard)}</div>
        <div className="pipeline-section-title"><i className="fa-solid fa-screwdriver-wrench"></i> Ferramentas do Agente</div>
        <div className="pipeline-section-desc">
          O LLM escolhe dinamicamente qual ferramenta usar com base no contexto atual. Cada ferramenta opera dentro do diretório <code>workspace/output/</code> da task e retorna resultados em texto.
        </div>
        <div className="pipeline-grid">{toolsList.map(renderToolCard)}</div>
        <div className="pipeline-section-title"><i className="fa-solid fa-person-walking-arrow-right"></i> Modo de Execução</div>
        <div className="pipeline-section-desc">
          Execução autônoma com execução direta de ferramentas. O usuário pode pausar a qualquer momento para intervir.
        </div>
        <div className="pipeline-info-cards">{modesCards.map(renderInfoCard)}</div>
      </div>
    </div>
  );
}

const mermaidCode = `graph TB
    subgraph Input["Input"]
        TASK["User Task"]
        MODE["Mode: Auto"]
        COMPLEX["Complexity: Simple / Complex"]
        MEM["Memory\\nSystem Prompt + Lessons"]
    end
    subgraph Orchestrator["Orchestrator"]
        direction TB
        VALIDATE["Validate Task"]
        INIT["Create Workspace"]
        CHECKPOINT["Checkpoint\\nAuto-Resume"]
    end
    subgraph Pipeline["Agent Pipeline"]
        direction TB
        P1["1. Generate Plan\\nLLM analisa e gera\\nplano detalhado"]
        P2["2. Create Steps\\nDivide em etapas\\nexecutaveis"]
        PA["Parallelism Analysis\\nAgrupa steps\\nindependentes"]
        P3["3. Execute Steps\\nLoop agente-ferramenta"]
        SUB_LOOP["LLM > Tool > Observe > Repeat\\nAuto: exec direta"]
    end
    subgraph Output["Output"]
        SUCCESS["Sucesso"]
        FAIL["Falha"]
        IMPROVE["Self-Improvement\\nExtrai licoes dos resultados"]
    end
    TASK --> VALIDATE
    MODE --> INIT
    COMPLEX --> INIT
    MEM --> P1
    MEM --> P3
    VALIDATE --> INIT
    INIT --> CHECKPOINT
    CHECKPOINT --> P1
    P1 --> P2
    P2 --> PA
    PA --> P3
    P3 --> SUB_LOOP
    SUB_LOOP -.->|finish_task| P3
    SUB_LOOP --> SUCCESS
    SUB_LOOP --> FAIL
    FAIL --> IMPROVE
    SUCCESS --> IMPROVE
    IMPROVE -.->|Licoes\\nalimentam\\nmemoria| MEM`;

const stages = [
  { icon: 'fa-check-double', title: '0. Validação & Inicialização', color: 'var(--text-muted)', description: 'Antes de iniciar o pipeline, o backend valida a requisição (task não vazia, parâmetros válidos), cria um diretório isolado workspace/{task_id}/ com subdiretório output/, e monta o state dict completo com status "running", stage "generating_plan", step 0, e metadados como mode, provider_type, max_steps. A execução roda em background thread liberando a API imediatamente.' },
  { icon: 'fa-layer-group', title: '1. Generate Plan', color: 'var(--color-primary)', description: 'O LLM recebe o prompt completo: tarefa do usuário + system prompt persistente + lições aprendidas de execuções anteriores. Gera um plano detalhado em markdown (plan.md) com análise do problema, arquitetura proposta e passos de alto nível. <br><br><b>Loop Detection:</b> Se respostas repetitivas são detectadas, um LoopDetectedError é levantado e o sistema retenta até MAX_STAGE_RETRIES (3).' },
  { icon: 'fa-list-tree', title: '2. Create Steps', color: 'var(--color-accent)', description: 'O LLM recebe o plano gerado e o divide em etapas executáveis. Cada etapa vira um objeto no array state["steps"] com: summary, description, status ("pending"|"completed"|"failed").<br><br><b>Análise de Paralelismo (Complex):</b> Para tarefas complexas, uma etapa adicional identifica steps independentes que podem ser executados simultaneamente via ParallelExecutor.<br><br><b>Checkpoint:</b> Após a criação, um checkpoint é salvo e o stage avança para "executing_steps".' },
  { icon: 'fa-rotate', title: '3. Execute Steps', color: 'var(--color-warning)', description: 'O coração do pipeline. Para cada etapa, o LLM entra em um loop de tool calls:<br><br>1. LLM decide qual ferramenta usar → gera JSON { tool, args }<br>2. Ferramenta é executada no workspace/output/<br>3. Resultado é retornado ao LLM como observação<br>4. LLM decide próximo passo ou chama finish_task<br><br><b>Auto Mode:</b> Tools executam automaticamente.' },
  { icon: 'fa-graduation-cap', title: '4. Self-Improvement', color: 'var(--color-secondary)', description: 'O sistema extrai lições diretamente dos resultados de execução, sem julgamentos de certo ou errado. A cada resultado (conclusão ou erro), o LLM analisa o contexto e gera uma lição estruturada { title, context, lesson } que é armazenada em memory/lessons.json. Na próxima task, todas as lições são carregadas como contexto adicional no prompt do LLM, permitindo que o agente melhore continuamente com base na experiência acumulada.' },
];

const infoCards = [
  { icon: 'fa-robot', title: 'MariaAgent', text: 'Orquestrador inteligente que coordena todo o pipeline: validação, plano, steps, execução e aprendizado. Gerencia estado, checkpoints e fluxo entre estágios.' },
  { icon: 'fa-microchip', title: 'LLM', text: 'Modelo de linguagem (LlamaCpp) que gera planos detalhados, decide ações, analisa resultados e extrai lições. Suporte a múltiplos nodes para balanceamento de carga.' },
  { icon: 'fa-screwdriver-wrench', title: 'Ferramentas', text: '12 ferramentas especializadas: list_dir, read_file, write_file, edit_file, edit_lines, grep, find_in_files, grep_output, run_lint, start/stop_http_server, finish_task.' },
  { icon: 'fa-brain', title: 'Memória Persistente', text: 'System prompt editável + lições aprendidas (lessons.json) carregadas automaticamente em cada execução para melhoria contínua e prevenção de erros recorrentes.' },
  { icon: 'fa-diagram-project', title: 'Paralelismo Inteligente', text: 'Para tarefas Complex, o ParallelExecutor analisa dependências entre steps e executa simultaneamente steps independentes, acelerando tasks com múltiplas frentes de trabalho.' },
  { icon: 'fa-floppy-disk', title: 'Checkpoint & Auto-Resume', text: 'Checkpoints salvos a cada transição de stage. Se o servidor reiniciar, tasks em execução são automaticamente restauradas e retomadas do ponto exato onde pararam.' },
  { icon: 'fa-shield', title: 'Segurança Integrada', text: 'Loop detection previne loops infinitos de ferramentas.' },
];

const flowSteps = [
  { icon: 'fa-pen-to-square', title: '1. Usuário cria uma tarefa', color: 'var(--color-primary)', description: 'No modal "New Agent Task", o usuário descreve a tarefa em linguagem natural e configura os parâmetros de execução:<br><br><b>Modo:</b> Auto (execução autônoma).<br><b>Complexidade:</b> Simple (execução direta sem arquitetura extra) ou Complex (implementação completa com análise de paralelismo).<br><b>Provedor LLM:</b> Múltiplos nodes LlamaCpp disponíveis para balanceamento de carga.<br><br><b>Parâmetros:</b> task, mode, complexity, provider_type, max_steps (default 20), max_retries (default 2).<br><br><b>Validação:</b> Backend rejeita tarefas sem descrição (HTTP 400) e limita steps para evitar loops infinitos.', details: 'Frontend → POST /api/tasks → Body JSON { task, mode, complexity, provider_type }' },
  { icon: 'fa-server', title: '2. Backend inicializa e dispara execução', color: 'var(--color-accent)', description: 'O Flask cria um ambiente isolado para a task:<br><br>1. Diretório workspace/{task_id}/ com subdiretório output/<br>2. State dict completo: status "running", stage "generating_plan", step 0<br>3. Metadados: mode, provider_type, max_steps, execution_log, proposed_tool<br><br><b>Thread background:</b> Execução roda em thread separada (run_agent_step_sync), liberando a API imediatamente.<br><br><b>Checkpoints:</b> Salvos em checkpoint.json a cada transição de stage.<br><br><b>Auto-Resume:</b> Ao reiniciar o servidor, tasks com status "running" ou "processando" são automaticamente restauradas dos checkpoints e retomadas.', details: 'Thread: run_agent_step_sync() → state dict → checkpoint.json → auto-resume' },
  { icon: 'fa-layer-group', title: '3. Geração do Plano (Generate Plan)', color: 'var(--color-primary)', description: 'O LLM recebe o prompt completo com: tarefa do usuário + system prompt persistente + lições aprendidas de execuções anteriores. Gera um plano detalhado em markdown com análise do problema, arquitetura proposta e passos de alto nível.<br><br><b>Salvamento:</b> workspace/{task_id}/plan.md.<br><br><b>Loop Detection:</b> Se o LLM entra em loop (respostas repetitivas), um LoopDetectedError é levantado. O sistema retenta até MAX_STAGE_RETRIES (3). Após 3 falhas, status → "failed" com motivo registrado em state["details"].', details: 'state["stage"]="generating_plan" → LLM → plan.md → stage_retries ≤ 3' },
  { icon: 'fa-list-tree', title: '4. Divisão em Etapas (Create Steps)', color: 'var(--color-accent)', description: 'O LLM recebe o plano e o divide em etapas executáveis. Cada etapa vira um objeto no array state["steps"]: { summary, description, status }.<br><br><b>Análise de Paralelismo (Complex):</b> Para tarefas complexas, uma etapa adicional identifica steps independentes que podem ser executados simultaneamente via ParallelExecutor, que gerencia tool calls concorrentes e coleta resultados.<br><br><b>Checkpoint:</b> Após a criação, checkpoint é salvo e stage avança para "executing_steps".<br><br><b>Error Handling:</b> Loop detection com MAX_STAGE_RETRIES (3). Se não conseguir dividir o plano, a task falha.', details: 'state["steps"] = [{ summary, description, status }] → ParallelExecutor para steps paralelos' },
  { icon: 'fa-rotate', title: '5. Execução das Etapas (Execute Steps)', color: 'var(--color-warning)', description: 'O coração do sistema. Para cada etapa, o LLM entra em um loop agente-ferramenta:<br><br>1. LLM decide qual ferramenta usar → gera JSON { tool, args }<br>2. Ferramenta é executada no workspace/output/<br>3. Resultado é retornado ao LLM como observação<br>4. LLM decide próximo passo ou chama finish_task<br><br><b>Auto Mode:</b> Tools executam automaticamente.<br><br><b>Loop Detection:</b> Se o LLM repete a mesma tool com args similares, um contador de repetição é incrementado. Ao atingir o limite, a task é pausada para intervenção.<br><br><b>Múltiplas Tools:</b> O LLM pode chamar várias tools em uma resposta, sequencialmente ou como array JSON.', details: 'Loop: LLM → decide tool → executa → observa → repete → finish_task' },
  { icon: 'fa-graduation-cap', title: '6. Self-Improvement (Aprendizado com Resultados)', color: 'var(--color-secondary)', description: 'O sistema extrai lições diretamente dos resultados de execução, sem julgamentos de certo ou errado:<br><br>1. A cada resultado (conclusão ou erro), o LLM analisa o contexto<br>2. Gera lição estruturada: { title, context, lesson }<br>3. Salva em memory/lessons.json<br>4. Na próxima task, lições são carregadas como contexto adicional no prompt do LLM<br><br><b>Visualização:</b> Botão "Lessons" no sidebar → modal com lista completa de lições.<br><br><b>System Prompt:</b> Diretrizes fixas de comportamento, editável via botão "Prompt" no sidebar.<br><br><b>Benefício:</b> O agente acumula experiência e melhora continuamente sem depender de julgamento externo.', details: 'Resultado → LLM analisa → lição { title, context, lesson } → memory/lessons.json' },
  { icon: 'fa-display', title: '7. Resultado exibido no Frontend em Tempo Real', color: 'var(--color-primary)', description: 'O frontend React+TypeScript polla a cada 1.2s o endpoint GET /api/tasks/{id} e atualiza toda a interface:<br><br><b>Logs de Execução:</b> Cards com role icons: system (servidor), assistant (robô), tool_result (terminal), supervisor (escudo). Metadados de LLM (tokens, velocidade) em cada entry.<br><br><b>Streaming:</b> Resposta do LLM em tempo real via current_streaming_response, mostrando os últimos 200 caracteres enquanto gera.<br><br><b>File Tree:</b> workspace/output/ exibido como tree clicável com ícones. Arquivos podem ser abertos no editor embutido com syntax highlighting.<br><br><b>Supervisor:</b> Se ativado, exibe banner com análise final após conclusão.', details: 'Polling 1.2s → fetchTaskDetails() → renderLogs + Stream + FileTree + AgentInfo' },
];

const toolsList = [
  { icon: 'fa-folder-open', name: 'list_dir', params: 'path="."', desc: 'Lista arquivos e diretórios dentro de workspace/output/. Retorna árvore com prefixos [DIR] e [FILE]. Oculta diretórios como node_modules, __pycache__, .venv. Ideal para explorar a estrutura do projeto.' },
  { icon: 'fa-file-lines', name: 'read_file', params: 'path', desc: 'Lê e retorna o conteúdo de um arquivo dentro de workspace/output/. Arquivos binários são detectados e rejeitados automaticamente. Sistema bloqueia leitura de task_state.json e task_info.html.' },
  { icon: 'fa-file-pen', name: 'write_file', params: 'path, content', desc: 'Escreve conteúdo em um arquivo. Diretórios intermediários são criados automaticamente. Caminhos absolutos são rejeitados. Retorna "Success: File written" ou mensagem de erro detalhada.' },
  { icon: 'fa-pen', name: 'edit_file', params: 'path, target, replacement', desc: 'Substitui a primeira ocorrência de um texto alvo por um novo texto em um arquivo. Case-sensitive. Útil para fazer alterações cirúrgicas sem reescrever o arquivo inteiro.' },
  { icon: 'fa-pen-to-square', name: 'edit_lines', params: 'path, start_line, end_line, replacement', desc: 'Substitui um intervalo de linhas (1-indexed, inclusivo) por novo texto. Mais preciso que edit_file para edições baseadas em linha. Retorna erro se linha estiver fora do range.' },
  { icon: 'fa-search', name: 'grep', params: 'path, pattern', desc: 'Busca por um padrão regex dentro de um arquivo específico. Retorna linhas correspondentes com números de linha. Se o padrão for inválido, retorna erro de regex.' },
  { icon: 'fa-magnifying-glass', name: 'find_in_files', params: 'query, path="."', desc: 'Busca por texto ou regex em múltiplos arquivos sob workspace/output/. Retorna filepath:linha: conteúdo. Resultados truncados em 200 matches. Se query for regex válido, usa como regex; senão, busca literal.' },
  { icon: 'fa-filter', name: 'grep_output', params: 'query', desc: 'Atalho que busca sempre na raiz de workspace/output/. Mesma lógica de regex/literal do find_in_files. Se o diretório output/ não existir, retorna erro específico.' },
  { icon: 'fa-broom', name: 'run_lint', params: 'language, path="."', desc: 'Executa linter nos arquivos gerados em workspace/output/. Suporta "python" (ruff) e "typescript" (eslint). Útil para verificar qualidade do código após geração.' },
  { icon: 'fa-server', name: 'start_http_server', params: 'port=10010, path="."', desc: 'Sobe um servidor HTTP estático (python -m http.server) dentro de workspace/output/ (ou subcaminho) na porta informada (padrão 10010) para que o usuário possa abrir e testar o HTML gerado no navegador. Retorna server_id, port, path e url. O servidor fica registrado na task e é encerrado automaticamente quando ela é deletada. Se a porta estiver ocupada, o tool falha com sugestão de porta livre próxima.' },
  { icon: 'fa-stop', name: 'stop_http_server', params: 'server_id', desc: 'Encerra um servidor HTTP previamente iniciado com start_http_server. Recebe o server_id retornado pelo start. Use list_http_servers para descobrir ids ativos.' },
  { icon: 'fa-list-ul', name: 'list_http_servers', params: '(nenhum)', desc: 'Lista todos os servidores HTTP ativos para a task atual, retornando server_id, port, path e url. Útil para descobrir ids antes de chamar stop_http_server.' },
  { icon: 'fa-flag-checkered', name: 'finish_task', params: 'summary', desc: 'Pseudo-tool de controle. Sinaliza que a etapa atual está completa. O orchestrator registra o summary em completed_step_summaries e avança para a próxima etapa ou para verificação se todas estiverem concluídas.' },
];

const modesCards = [
  { icon: 'fa-rocket', title: 'Modo Auto (Autônomo)', text: 'Execução autônoma com execução direta de ferramentas. O usuário pode pausar a qualquer momento para intervir. Ideal para tarefas rotineiras, bem definidas ou quando o usuário confia na capacidade do agente.' },
];

function renderStageCard(s: typeof stages[0], idx: number) {
  return (
    <div key={idx} className="pipeline-stage-card">
      <div className="pipeline-stage-header" style={{ '--stage-color': s.color } as any}>
        <i className={`fa-solid ${s.icon}`}></i>
        <span>{s.title}</span>
      </div>
      <div className="pipeline-stage-body">
        <p dangerouslySetInnerHTML={{ __html: s.description }} />
      </div>
    </div>
  );
}

function renderInfoCard(c: typeof infoCards[0], idx: number) {
  return (
    <div key={idx} className="pipeline-card">
      <div className="pipeline-card-icon"><i className={`fa-solid ${c.icon}`}></i></div>
      <div className="pipeline-card-content">
        <div className="pipeline-card-title">{c.title}</div>
        <div className="pipeline-card-text">{c.text}</div>
      </div>
    </div>
  );
}

function renderFlowCard(s: typeof flowSteps[0], idx: number) {
  return (
    <div key={idx} className="pipeline-flow-card">
      <div className="pipeline-flow-icon" style={{ background: `color-mix(in srgb, ${s.color} 12%, var(--bg-surface))`, color: s.color }}>
        <i className={`fa-solid ${s.icon}`}></i>
      </div>
      <div className="pipeline-flow-content">
        <div className="pipeline-flow-title" style={{ color: s.color }}>{s.title}</div>
        <div className="pipeline-flow-desc" dangerouslySetInnerHTML={{ __html: s.description }} />
        <div className="pipeline-flow-detail">
          <i className="fa-solid fa-code"></i> {s.details}
        </div>
      </div>
    </div>
  );
}

function renderToolCard(t: typeof toolsList[0], idx: number) {
  return (
    <div key={idx} className="pipeline-grid-card">
      <div className="pipeline-grid-icon"><i className={`fa-solid ${t.icon}`}></i></div>
      <div className="pipeline-grid-body">
        <div className="pipeline-grid-name">{t.name}</div>
        <div className="pipeline-grid-params">{t.params}</div>
        <div className="pipeline-grid-desc">{t.desc}</div>
      </div>
    </div>
  );
}
