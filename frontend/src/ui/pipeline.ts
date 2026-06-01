import { $, el, show, hide } from '../utils/dom';

const mermaidCode = `graph TB
    subgraph Input["Input"]
        TASK[User Task]
        MEM[Memory \\nSystem Prompt + Lessons]
    end

    subgraph Pipeline["Agent Pipeline"]
        direction TB
        P1["1. Generate Plan\\nLLM cria um plano\\ndetalhado de execução"]
        P2["2. Create Steps\\nPlano é dividido em\\netapas executáveis"]
        P3["3. Execute Steps\\nLoop agente-ferramenta:\\nLLM decide → executa →\\nobserva → repete"]
        P4["4. Verify Execution\\nVerifica se o plano\\nfoi totalmente cumprido"]
    end

    subgraph Output["Output"]
        SUCCESS[Sucesso] --> VERDICT{Veredito}
        FAIL[Falha] --> VERDICT
        IMPROVE[Self-Improvement\\nExtrai lições de erros]
    end

    TASK --> P1
    MEM --> P1
    MEM --> P3
    P1 --> P2
    P2 --> P3
    P3 --> P4
    P4 --> SUCCESS
    P4 --> FAIL
    FAIL --> IMPROVE
    IMPROVE -.->|Lições\\nalimentam\\nmemória| MEM`;

const stages = [
  {
    icon: 'fa-solid fa-layer-group',
    title: '1. Generate Plan',
    color: 'var(--color-primary)',
    description:
      'O LLM recebe a tarefa do usuário e gera um plano completo de execução. Este plano é salvo em plan.md no workspace e inclui uma análise detalhada do problema, arquitetura proposta, e passos de alto nível.',
  },
  {
    icon: 'fa-solid fa-list-tree',
    title: '2. Create Steps',
    color: 'var(--color-accent)',
    description:
      'O plano é dividido em etapas menores e executáveis. Cada etapa representa uma unidade de trabalho que o agente pode processar sequencialmente. As etapas são armazenadas como uma lista numerada.',
  },
  {
    icon: 'fa-solid fa-rotate',
    title: '3. Execute Steps',
    color: 'var(--color-warning)',
    description:
      'O coração do pipeline. Para cada etapa, o LLM decide qual ferramenta usar (list_dir, read_file, write_file, run_command, etc.), executa a ação, observa o resultado, e decide o próximo passo. Ferramentas disponíveis: list_dir, read_file, write_file, edit_file, grep, run_command, finish_task.',
  },
  {
    icon: 'fa-solid fa-check-double',
    title: '4. Verify Execution',
    color: 'var(--color-success)',
    description:
      'Após todas as etapas serem executadas, o sistema verifica se o plano foi completamente cumprido. Gera um relatório de análise e um veredito final: SUCCESS ou FAILED. O relatório é salvo em verification_report.md.',
  },
  {
    icon: 'fa-solid fa-graduation-cap',
    title: '5. Self-Improvement',
    color: 'var(--color-secondary)',
    description:
      'Quando ocorrem erros, o sistema extrai lições aprendidas e as armazena na memória persistente. Essas lições são carregadas no início do próximo pipeline, permitindo que o agente melhore continuamente e evite repetir os mesmos erros.',
  },
];

const stageLabels: Record<string, string> = {
  generating_plan: '1. Generate Plan',
  creating_steps: '2. Create Steps',
  analyzing_parallelism: 'Parallelism Analysis',
  executing_steps: '3. Execute Steps',
  verifying: '4. Verify Execution',
};

const stageIcons: Record<string, string> = {
  generating_plan: 'fa-layer-group',
  creating_steps: 'fa-list-tree',
  analyzing_parallelism: 'fa-diagram-project',
  executing_steps: 'fa-rotate',
  verifying: 'fa-check-double',
};

const stageCardIdx: Record<string, number> = {
  generating_plan: 0,
  creating_steps: 1,
  executing_steps: 2,
  verifying: 3,
};

let initialized = false;
let currentTheme = '';
let prevStatus: string | null = null;
let continuedFlashTimer: ReturnType<typeof setTimeout> | null = null;

function getMermaidTheme(): 'dark' | 'default' {
  const theme = document.documentElement.getAttribute('data-theme') ?? 'light';
  return theme === 'dark' ? 'dark' : 'default';
}

function getMermaidVars(isDark: boolean) {
  if (isDark) {
    return {
      background: '#1b1e2e',
      primaryColor: '#6366f1',
      primaryTextColor: '#ffffff',
      primaryBorderColor: '#818cf8',
      lineColor: '#818cf8',
      secondaryColor: '#1e1b4b',
      tertiaryColor: '#0c4a6e',
      clusterBkg: 'rgba(30,27,75,0.35)',
      clusterBorder: 'rgba(129,140,248,0.25)',
      nodeBorder: '#818cf8',
      nodeTextColor: '#f8fafc',
      edgeLabelBackground: '#252a3e',
      edgeLabelColor: '#94a3b8',
      titleColor: '#f8fafc',
    };
  }
  return {
    background: '#ffffff',
    primaryColor: '#3b82f6',
    primaryTextColor: '#ffffff',
    primaryBorderColor: '#6366f1',
    lineColor: '#6366f1',
    secondaryColor: '#eef2ff',
    tertiaryColor: '#f0f9ff',
    clusterBkg: 'rgba(238,242,255,0.5)',
    clusterBorder: 'rgba(99,102,241,0.2)',
    nodeBorder: '#6366f1',
    nodeTextColor: '#1e293b',
    edgeLabelBackground: '#ffffff',
    edgeLabelColor: '#475569',
    titleColor: '#1e293b',
  };
}

function renderDiagram(): string {
  return `<div class="mermaid">${mermaidCode}</div>`;
}

function renderLiveStatus(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'pipeline-live-status';
  el.style.display = 'none';
  el.innerHTML = `
    <div class="pipeline-live-inner">
      <div class="pipeline-live-head">
        <span class="pipeline-live-badge"></span>
        <span class="pipeline-live-stage-label"></span>
        <span class="pipeline-live-step-label"></span>
      </div>
      <div class="pipeline-live-task-desc"></div>
    </div>
  `;
  return el;
}

export function updatePipelineTaskStatus(task: {
  task_id: string;
  task: string;
  status: string;
  step?: number;
  stage?: string;
  stage_retries?: number;
  details?: string;
}): void {
  const liveSection = document.querySelector('.pipeline-live-status') as HTMLElement | null;
  if (!liveSection) return;

  const isActive = task.status === 'running' || task.status === 'processando';
  const isFailed = task.status === 'failed';
  const isCompleted = task.status === 'completed';
  const isAwaiting = task.status === 'awaiting_intervention';
  const isRetrying = isActive && (task.stage_retries ?? 0) > 0;
  const wasContinued = prevStatus === 'failed' && isActive;
  prevStatus = task.status;

  if (!isActive && !isFailed && !isCompleted && !isAwaiting) {
    hide(liveSection);
    clearStageHighlights();
    return;
  }

  show(liveSection);

  const badge = liveSection.querySelector('.pipeline-live-badge');
  if (badge) {
    if (isRetrying) {
      badge.className = 'pipeline-live-badge status-retrying';
      badge.innerHTML = '<i class="fa-solid fa-rotate fa-spin"></i> Retrying';
    } else if (wasContinued) {
      badge.className = 'pipeline-live-badge status-continued';
      badge.innerHTML = '<i class="fa-solid fa-forward"></i> Continued';
      if (continuedFlashTimer) clearTimeout(continuedFlashTimer);
      continuedFlashTimer = setTimeout(() => {
        const b = document.querySelector('.pipeline-live-badge');
        if (b) {
          b.className = 'pipeline-live-badge status-running';
          b.innerHTML = '<i class="fa-solid fa-circle" style="color: var(--color-running); font-size: 8px;"></i> Running';
        }
      }, 5000);
    } else if (isActive || isAwaiting) {
      badge.className = 'pipeline-live-badge status-running';
      badge.innerHTML = '<i class="fa-solid fa-circle" style="color: var(--color-running);"></i> ' + (isAwaiting ? 'Awaiting' : 'Running');
    } else if (isFailed) {
      badge.className = 'pipeline-live-badge status-failed';
      badge.innerHTML = '<i class="fa-solid fa-circle-xmark"></i> Failed';
    } else if (isCompleted) {
      badge.className = 'pipeline-live-badge status-completed';
      badge.innerHTML = '<i class="fa-solid fa-circle-check"></i> Completed';
    }
  }

  const stageLabel = liveSection.querySelector('.pipeline-live-stage-label');
  if (stageLabel && task.stage) {
    const displayName = stageLabels[task.stage] ?? task.stage;
    const icon = stageIcons[task.stage] ?? 'fa-circle';
    stageLabel.innerHTML = `<i class="fa-solid ${icon}"></i> ${displayName}`;
  }

  const stepLabel = liveSection.querySelector('.pipeline-live-step-label');
  if (stepLabel) {
    stepLabel.textContent = `Step ${task.step ?? 0}`;
  }

  const desc = liveSection.querySelector('.pipeline-live-task-desc');
  if (desc) {
    desc.textContent = task.task;
  }

  highlightStageCards(task.stage, task.status, task.stage_retries);
}

function clearStageHighlights(): void {
  const cards = document.querySelectorAll('.pipeline-stage-card');
  cards.forEach(c => {
    c.classList.remove('stage-active', 'stage-failed', 'stage-completed', 'stage-retrying', 'stage-awaiting');
    const existingBadge = c.querySelector('.pipeline-stage-status');
    if (existingBadge) existingBadge.remove();
  });
}

function highlightStageCards(stage?: string, status?: string, stageRetries?: number): void {
  const cards = document.querySelectorAll('.pipeline-stage-card');
  clearStageHighlights();

  const idx = stage ? stageCardIdx[stage] : -1;
  if (idx < 0 || idx >= cards.length) return;

  const card = cards[idx] as HTMLElement;
  const isFailed = status === 'failed';
  const isRunning = status === 'running' || status === 'processando';
  const isAwaiting = status === 'awaiting_intervention';
  const isCompleted = status === 'completed';
  const isRetrying = isRunning && (stageRetries ?? 0) > 0;

  if (isFailed) {
    card.classList.add('stage-failed');
    addStageBadge(card, 'failed', '<i class="fa-solid fa-circle-xmark"></i> Failed');
  } else if (isRetrying) {
    card.classList.add('stage-retrying');
    addStageBadge(card, 'retrying', '<i class="fa-solid fa-rotate fa-spin"></i> Retrying');
  } else if (isCompleted) {
    card.classList.add('stage-completed');
    addStageBadge(card, 'completed', '<i class="fa-solid fa-circle-check"></i> Completed');
  } else if (isAwaiting) {
    card.classList.add('stage-awaiting');
    addStageBadge(card, 'awaiting', '<i class="fa-solid fa-clock"></i> Awaiting');
  } else if (isRunning) {
    card.classList.add('stage-active');
    addStageBadge(card, 'active', '<i class="fa-solid fa-circle-notch fa-spin"></i> Active');
  }
}

function addStageBadge(card: HTMLElement, className: string, html: string): void {
  const existing = card.querySelector<HTMLElement>('.pipeline-stage-status');
  if (existing) existing.remove();
  const badge = document.createElement('span');
  badge.className = `pipeline-stage-status ${className}`;
  badge.innerHTML = html;
  card.querySelector('.pipeline-stage-header')?.appendChild(badge);
}

function renderStages(): HTMLElement {
  const container = el('div', { className: 'pipeline-stages' });
  for (const s of stages) {
    const card = el('div', { className: 'pipeline-stage-card' });
    card.innerHTML = `
      <div class="pipeline-stage-header" style="--stage-color: ${s.color}">
        <i class="${s.icon}"></i>
        <span>${s.title}</span>
      </div>
      <div class="pipeline-stage-body">
        <p>${s.description}</p>
      </div>
    `;
    container.appendChild(card);
  }
  return container;
}

function renderAppFlow(): HTMLElement {
  const container = el('div', { className: 'pipeline-flow' });

  const flowSteps = [
    {
      icon: 'fa-solid fa-pen-to-square',
      title: '1. Usuário cria uma tarefa',
      color: 'var(--color-primary)',
      description: 'No modal "New Agent Task", o usuário descreve a tarefa em linguagem natural, seleciona o modo de execução (Auto ou Step), a complexidade (Simple — execução direta sem arquitetura extra; Complex — implementação completa com arquitetura) e o provedor LLM (LlamaCpp Node 1 em 192.168.20.180 ou Node 2 em 192.168.20.181).<br><br><b>Parâmetros enviados:</b> task (string), mode ("step"|"auto"), complexity ("simple"|"complex"), provider_type ("llamacpp"|"llamacpp_2"), max_steps (default 20), max_retries (default 2).<br><br><b>Validação:</b> O backend rejeita tarefas sem descrição (HTTP 400) e limita o número de steps para evitar loops infinitos.',
      details: 'Frontend → POST /api/tasks → Body JSON { task, mode, complexity, provider_type }',
    },
    {
      icon: 'fa-solid fa-server',
      title: '2. Backend inicializa e dispara execução',
      color: 'var(--color-accent)',
      description: 'O Flask cria um diretório isolado workspace/{task_id}/ com subdiretório output/. Escreve task_info.html (metadados legados), depois monta o state dict completo. O estado inicial contém: status "running", stage "generating_plan", step 0, execution_log com entry system inicial, proposed_tool { name: "generate_plan" }, mode, provider_type, max_steps, e lista vazia de steps/errors.<br><br><b>Thread background:</b> A execução do agente roda em uma thread separada (run_agent_step_sync), liberando a API imediatamente. Checkpoints são salvos em checkpoint.json a cada transição de stage.<br><br><b>Resume automático:</b> Ao reiniciar o servidor, tasks com status "running" ou "processando" são automaticamente restauradas dos checkpoints e retomadas.',
      details: 'Thread: run_agent_step_sync() → state dict → checkpoints em checkpoint.json',
    },
    {
      icon: 'fa-solid fa-layer-group',
      title: '3. Geração do Plano (Generate Plan)',
      color: 'var(--color-primary)',
      description: 'O LLM recebe o prompt completo: tarefa do usuário + system prompt persistente + lições aprendidas de execuções anteriores. Ele deve gerar um plano detalhado de execução em markdown, analisando o problema, propondo arquitetura e listando passos de alto nível.<br><br><b>Salvamento:</b> O plano é salvo em workspace/{task_id}/plan.md.<br><br><b>Retry com loop detection:</b> Se o LLM entrar em loop (respostas repetitivas), um LoopDetectedError é levantado. O sistema incrementa state["stage_retries"] e retenta. Após MAX_STAGE_RETRIES (3) tentativas sem sucesso, o status muda para "failed" e o motivo é registrado em state["details"].<br><br><b>Modo Step:</b> Ao concluir o plano em modo Step, o status muda para "awaiting_intervention", permitindo que o usuário revise o plano antes de prosseguir.',
      details: 'state["stage"]="generating_plan" → LLM → plan.md → stage_retries ≤ 3',
    },
    {
      icon: 'fa-solid fa-list-tree',
      title: '4. Divisão em Etapas (Create Steps)',
      color: 'var(--color-accent)',
      description: 'O LLM recebe o plano gerado e o divide em etapas executáveis. Cada etapa vira um objeto no array state["steps"] com: summary (resumo), description (detalhes), status ("pending"|"completed"|"failed").<br><br><b>Análise de paralelismo (complex):</b> Para tarefas complexas, uma etapa adicional de análise identifica quais steps podem ser executados em paralelo. Steps independentes são agrupados e executados simultaneamente via ParallelExecutor, que gerencia tool calls concorrentes e coleta resultados.<br><br><b>Checkpoint:</b> Após a criação, um checkpoint é salvo com os steps e o stage avança para "executing_steps".<br><br><b>Error handling:</b> Mesmo sistema de loop detection com MAX_STAGE_RETRIES (3). Se o LLM não conseguir dividir o plano corretamente, a task falha.',
      details: 'state["steps"] = [{ summary, description, status }] → ParallelExecutor para steps independentes',
    },
    {
      icon: 'fa-solid fa-rotate',
      title: '5. Execução das Etapas (Execute Steps)',
      color: 'var(--color-warning)',
      description: 'O coração do sistema. Para cada etapa, o LLM entra em um loop de tool calls:<br><br>1. LLM decide qual ferramenta usar e gera JSON: {"tool": "tool_name", "args": {...}}<br>2. Ferramenta é executada no workspace/output/<br>3. Resultado é retornado ao LLM como observação<br>4. LLM decide próximo passo ou chama finish_task<br><br><b>Em modo Step:</b> Após cada tool call, o status muda para "awaiting_intervention". O usuário vê o tool proposto no painel de intervenção e pode: Approve (aprovar e executar), Modify (modificar args e executar), ou Continue (pular).<br><br><b>Em modo Auto:</b> Ferramentas não-sensíveis são executadas automaticamente. Comandos críticos (rm, git, docker, npm, curl, etc.) são verificados por is_command_critical() e exigem aprovação mesmo em modo Auto.<br><br><b>Loop detection:</b> Se o LLM repete a mesma tool com args similares, um contador de repetição é incrementado. Ao atingir o limite, a task é pausada para intervenção ou falha.<br><br><b>Múltiplas tools:</b> O LLM pode chamar várias tools em uma resposta, seja sequencialmente ou como array JSON.',
      details: 'Loop: LLM → decide tool → executa → observa → repete → finish_task',
    },
    {
      icon: 'fa-solid fa-check-double',
      title: '6. Verificação (Verify Execution)',
      color: 'var(--color-success)',
      description: 'Após todas as etapas serem concluídas (finish_task chamado com sucesso para cada step), o sistema entra no stage "verifying". O LLM recebe o plano original + resumo das etapas executadas + resultados e gera um relatório de verificação.<br><br><b>Relatório:</b> Salvo em workspace/{task_id}/verification_report.md, contendo análise detalhada do que foi cumprido vs. o que faltou.<br><br><b>Veredito:</b> O LLM decide SUCCESS (plano cumprido) ou FAILED (algo não foi implementado corretamente). Se FAILED, a task é marcada como "failed" com detalhes do motivo.<br><br><b>Retry:</b> Se a verificação detectar um loop (LLM gerando relatórios repetitivos), o sistema retenta até MAX_STAGE_RETRIES antes de falhar definitivamente.',
      details: 'state["stage"]="verifying" → LLM compara plano × execução → SUCCESS | FAILED',
    },
    {
      icon: 'fa-solid fa-graduation-cap',
      title: '7. Self-Improvement (Aprendizado com Erros)',
      color: 'var(--color-secondary)',
      description: 'Quando uma task falha, o sistema automaticamente extrai lições do erro. O processo:<br><br>1. O LLM analisa o erro (motivo da falha, tool que causou o erro, estágio onde ocorreu)<br>2. Gera uma lição estruturada com: título, descrição do erro, resolução recomendada<br>3. A lição é salva em memory/lessons.json<br>4. Na próxima task, todas as lições são carregadas como contexto adicional no prompt do LLM<br><br><b>Formato da lição:</b> { title: string, error: string, resolution: string }.<br><br><b>Visualização:</b> O usuário pode ver todas as lições acumuladas clicando no botão "Lessons" no sidebar, que abre um modal com a lista completa.<br><br><b>System Prompt:</b> Além das lições, o system prompt persistente (editável via botão "Prompt" no sidebar) fornece diretrizes fixas de comportamento para o agente.',
      details: 'Erro → LLM analisa → lição { title, error, resolution } → memory/lessons.json',
    },
    {
      icon: 'fa-solid fa-display',
      title: '8. Resultado exibido no Frontend em Tempo Real',
      color: 'var(--color-primary)',
      description: 'O frontend Vite+TypeScript polla a cada 1.2s o endpoint GET /api/tasks/{id} e atualiza a interface:<br><br><b>Logs de execução:</b> Cards com role icons: system (servidor), assistant (robô), tool_result (terminal), user_intervention (usuário), supervisor (escudo). Cada log mostra o step number e metadados de LLM (tokens, velocidade).<br><br><b>Streaming:</b> Quando o LLM está gerando, a resposta é transmitida em tempo real via current_streaming_response, mostrando os últimos 200 caracteres.<br><br><b>Árvore de arquivos:</b> workspace/output/ exibido como tree clicável, com ícones de pasta/arquivo. Arquivos podem ser abertos no editor embutido.<br><br><b>Intervenção:</b> Em modo Step, o console de intervenção mostra a tool proposta com seus argumentos, permitindo aprovar, modificar ou continuar.<br><br><b>Supervisor:</b> Se ativado, exibe banner com análise final do supervisor após conclusão.',
      details: 'Polling 1.2s → fetchTaskDetails() → renderLogs + Stream + FileTree + AgentInfo + Intervention',
    },
  ];

  for (const s of flowSteps) {
    const card = el('div', { className: 'pipeline-flow-card' });
    card.innerHTML = `
      <div class="pipeline-flow-icon" style="background: color-mix(in srgb, ${s.color} 12%, var(--bg-surface)); color: ${s.color};">
        <i class="${s.icon}"></i>
      </div>
      <div class="pipeline-flow-content">
        <div class="pipeline-flow-title" style="color: ${s.color};">${s.title}</div>
        <div class="pipeline-flow-desc">${s.description}</div>
        <div class="pipeline-flow-detail">
          <i class="fa-solid fa-code"></i>
          ${s.details}
        </div>
      </div>
    `;
    container.appendChild(card);
  }

  return container;
}

const toolsList = [
  { icon: 'fa-solid fa-folder-open', name: 'list_dir', params: 'path="."', desc: 'Lista arquivos e diretórios dentro de workspace/output/. Retorna árvore com prefixos [DIR] e [FILE]. Oculta diretórios como node_modules, __pycache__, .venv. Ideal para explorar a estrutura do projeto.' },
  { icon: 'fa-solid fa-file-lines', name: 'read_file', params: 'path', desc: 'Lê e retorna o conteúdo de um arquivo dentro de workspace/output/. Arquivos binários são detectados e rejeitados automaticamente. Sistema bloqueia leitura de task_state.json e task_info.html.' },
  { icon: 'fa-solid fa-file-pen', name: 'write_file', params: 'path, content', desc: 'Escreve conteúdo em um arquivo. Diretórios intermediários são criados automaticamente. Caminhos absolutos são rejeitados. Retorna "Success: File written" ou mensagem de erro detalhada.' },
  { icon: 'fa-solid fa-pen', name: 'edit_file', params: 'path, target, replacement', desc: 'Substitui a primeira ocorrência de um texto alvo por um novo texto em um arquivo. Case-sensitive. Útil para fazer alterações cirúrgicas sem reescrever o arquivo inteiro.' },
  { icon: 'fa-solid fa-pen-to-square', name: 'edit_lines', params: 'path, start_line, end_line, replacement', desc: 'Substitui um intervalo de linhas (1-indexed, inclusivo) por novo texto. Mais preciso que edit_file para edições baseadas em linha. Retorna erro se linha estiver fora do range.' },
  { icon: 'fa-solid fa-search', name: 'grep', params: 'path, pattern', desc: 'Busca por um padrão regex dentro de um arquivo específico. Retorna linhas correspondentes com números de linha. Se o padrão for inválido, retorna erro de regex.' },
  { icon: 'fa-solid fa-magnifying-glass', name: 'find_in_files', params: 'query, path="."', desc: 'Busca por texto ou regex em múltiplos arquivos sob workspace/output/. Retorna filepath:linha: conteúdo. Resultados truncados em 200 matches. Se query for regex válido, usa como regex; senão, busca literal.' },
  { icon: 'fa-solid fa-filter', name: 'grep_output', params: 'query', desc: 'Atalho que busca sempre na raiz de workspace/output/. Mesma lógica de regex/literal do find_in_files. Se o diretório output/ não existir, retorna erro específico.' },
  { icon: 'fa-solid fa-terminal', name: 'run_command', params: 'command', desc: 'Executa comando shell dentro de workspace/output/. Timeout de 600s. Comandos críticos (rm, git, docker, npm, curl, etc.) exigem aprovação mesmo em modo Auto. Processo é rastreado por PID e morto se a task for deletada. Retorna output formatado com exit code e duração.' },
  { icon: 'fa-solid fa-server', name: 'start_http_server', params: 'port=10010, path="."', desc: 'Sobe um servidor HTTP estático (python -m http.server) dentro de workspace/output/ (ou subcaminho) na porta informada (padrão 10010) para que o usuário possa abrir e testar o HTML gerado no navegador. Retorna server_id, port, path e url. O servidor fica registrado na task e é encerrado automaticamente quando ela é deletada. Se a porta estiver ocupada, o tool falha com sugestão de porta livre próxima.' },
  { icon: 'fa-solid fa-stop', name: 'stop_http_server', params: 'server_id', desc: 'Encerra um servidor HTTP previamente iniciado com start_http_server. Recebe o server_id retornado pelo start. Use list_http_servers para descobrir ids ativos.' },
  { icon: 'fa-solid fa-list-ul', name: 'list_http_servers', params: '(nenhum)', desc: 'Lista todos os servidores HTTP ativos para a task atual, retornando server_id, port, path e url. Útil para descobrir ids antes de chamar stop_http_server.' },
  { icon: 'fa-solid fa-flag-checkered', name: 'finish_task', params: 'summary', desc: 'Pseudo-tool de controle. Sinaliza que a etapa atual está completa. O orchestrator registra o summary em completed_step_summaries e avança para a próxima etapa ou para verificação se todas estiverem concluídas.' },
];

function renderTools(): HTMLElement {
  const container = el('div', { className: 'pipeline-grid' });
  for (const t of toolsList) {
    const card = el('div', { className: 'pipeline-grid-card' });
    card.innerHTML = `
      <div class="pipeline-grid-icon"><i class="${t.icon}"></i></div>
      <div class="pipeline-grid-body">
        <div class="pipeline-grid-name">${t.name}</div>
        <div class="pipeline-grid-params">${t.params}</div>
        <div class="pipeline-grid-desc">${t.desc}</div>
      </div>
    `;
    container.appendChild(card);
  }
  return container;
}

function renderModesDetail(): HTMLElement {
  const container = el('div', { className: 'pipeline-info-cards' });
  const cards = [
    { icon: 'fa-solid fa-robot', title: 'Modo Step (Passo a Passo)', color: 'var(--color-primary)', text: 'Após cada ferramenta proposta pelo LLM, o status muda para "awaiting_intervention". O usuário vê a tool + argumentos no console de intervenção e pode: <b>Approve</b> (aprovar e executar), <b>Modify</b> (editar args antes de executar), ou <b>Continue</b> (pular esta ferramenta). Ideal para aprendizado, debugging ou tarefas sensíveis onde cada ação deve ser supervisionada.' },
    { icon: 'fa-solid fa-rocket', title: 'Modo Auto (Autônomo)', color: 'var(--color-success)', text: 'Ferramentas não-sensíveis são executadas automaticamente sem intervenção. Apenas comandos críticos (rm, git, docker, npm, curl, etc.) disparam verificação de segurança via is_command_critical(). O usuário pode intervir a qualquer momento pausando a execução. Ideal para tarefas rotineiras e bem definidas.' },
  ];
  for (const c of cards) {
    const card = el('div', { className: 'pipeline-card' });
    card.innerHTML = `
      <div class="pipeline-card-icon" style="background: color-mix(in srgb, ${c.color} 12%, var(--bg-surface)); color: ${c.color};"><i class="${c.icon}"></i></div>
      <div class="pipeline-card-content">
        <div class="pipeline-card-title">${c.title}</div>
        <div class="pipeline-card-text">${c.text}</div>
      </div>
    `;
    container.appendChild(card);
  }
  return container;
}

function renderInfoCards(): HTMLElement {
  const container = el('div', { className: 'pipeline-info-cards' });

  const cards = [
    {
      icon: 'fa-solid fa-robot',
      title: 'Agente',
      text: 'MariaAgent coordena todo o pipeline, orquestrando LLM, ferramentas e memória.',
    },
    {
      icon: 'fa-solid fa-microchip',
      title: 'LLM',
      text: 'Modelo de linguagem (Ollama/LlamaCpp) que gera planos, decide ações e analisa resultados.',
    },
    {
      icon: 'fa-solid fa-screwdriver-wrench',
      title: 'Ferramentas',
      text: 'O agente usa ferramentas como leitura/escrita de arquivos, execução de comandos e busca em arquivos.',
    },
    {
      icon: 'fa-solid fa-brain',
      title: 'Memória',
      text: 'System prompt persistente + lições aprendidas de execuções anteriores para melhoria contínua.',
    },
    {
      icon: 'fa-solid fa-person-walking-arrow-right',
      title: 'Modos',
      text: 'Step (aprovação manual a cada ação) e Auto (execução autônoma com aprovação apenas para comandos sensíveis).',
    },
    {
      icon: 'fa-solid fa-shield-halved',
      title: 'Supervisor',
      text: 'Revisor opcional que analisa o resultado final e fornece feedback para melhoria.',
    },
  ];

  for (const card of cards) {
    const div = el('div', { className: 'pipeline-card' });
    div.innerHTML = `
      <div class="pipeline-card-icon"><i class="${card.icon}"></i></div>
      <div class="pipeline-card-content">
        <div class="pipeline-card-title">${card.title}</div>
        <div class="pipeline-card-text">${card.text}</div>
      </div>
    `;
    container.appendChild(div);
  }

  return container;
}

function renderTitle(): HTMLElement {
  const header = el('div', { className: 'pipeline-header' });
  header.innerHTML = `
    <div class="pipeline-header-title">
      <i class="fa-solid fa-sitemap"></i>
      Pipeline Agent — Como Funciona
    </div>
    <div class="pipeline-header-subtitle">
      O Maria Agent segue um pipeline de múltiplos estágios para completar tarefas de codificação de forma autônoma.
      Cada estágio transforma a saída do anterior, culminando em um resultado verificado.
    </div>
  `;
  return header;
}

export function renderPipeline(containerId = 'pipeline-container'): void {
  const container = $(`#${containerId}`);
  if (!container) return;

  const theme = getMermaidTheme();

  if (!initialized || currentTheme !== theme) {
    container.innerHTML = '';
    currentTheme = theme;

    container.appendChild(renderTitle());
    container.appendChild(renderLiveStatus());

    const diagramWrapper = el('div', { className: 'pipeline-diagram-wrapper' });
    diagramWrapper.innerHTML = renderDiagram();
    container.appendChild(diagramWrapper);

    const stagesTitle = el('div', { className: 'pipeline-section-title' });
    stagesTitle.innerHTML = '<i class="fa-solid fa-list-ol"></i> Estágios do Pipeline';
    container.appendChild(stagesTitle);
    container.appendChild(renderStages());

    const componentsTitle = el('div', { className: 'pipeline-section-title' });
    componentsTitle.innerHTML = '<i class="fa-solid fa-cubes"></i> Componentes do Sistema';
    container.appendChild(componentsTitle);
    container.appendChild(renderInfoCards());

    const flowTitle = el('div', { className: 'pipeline-section-title' });
    flowTitle.innerHTML = '<i class="fa-solid fa-arrow-right-arrow-left"></i> Fluxo Completo da Aplicação';
    container.appendChild(flowTitle);
    container.appendChild(renderAppFlow());

    const toolsTitle = el('div', { className: 'pipeline-section-title' });
    toolsTitle.innerHTML = '<i class="fa-solid fa-screwdriver-wrench"></i> Ferramentas do Agente';
    container.appendChild(toolsTitle);

    const toolsDesc = el('div', { className: 'pipeline-section-desc' });
    toolsDesc.textContent = 'O LLM escolhe qual ferramenta usar com base no contexto. Cada ferramenta opera dentro do diretório workspace/output/ da task e retorna resultados em texto. Comandos críticos (rm, git, docker, npm, etc.) exigem aprovação de segurança.';
    container.appendChild(toolsDesc);

    container.appendChild(renderTools());

    const modesTitle = el('div', { className: 'pipeline-section-title' });
    modesTitle.innerHTML = '<i class="fa-solid fa-person-walking-arrow-right"></i> Modos de Execução';
    container.appendChild(modesTitle);
    container.appendChild(renderModesDetail());

    initialized = true;

    try {
      const m = (window as any).mermaid;
      m.initialize({
        startOnLoad: false,
        theme: 'base',
        themeVariables: getMermaidVars(currentTheme === 'dark'),
        flowchart: { useMaxWidth: true, htmlLabels: true, padding: 16 },
      });
      m.run({ nodes: [diagramWrapper.querySelector('.mermaid')] });
    } catch {
      setTimeout(() => {
        try {
          const m = (window as any).mermaid;
          m.initialize({
            startOnLoad: false,
            theme: 'base',
            themeVariables: getMermaidVars(currentTheme === 'dark'),
            flowchart: { useMaxWidth: true, htmlLabels: true, padding: 16 },
          });
          m.run({ nodes: [diagramWrapper.querySelector('.mermaid')] });
        } catch {}
      }, 100);
    }
  }
}

export function resetPipelineRender(): void {
  initialized = false;
}

export function initPipeline(): void {
  const container = $('#pipeline-container');
  if (!container) return;

  renderPipeline();
}
