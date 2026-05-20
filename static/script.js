let currentTaskId = null;
let activePollingInterval = null;
let editingFilePath = null;
let executionLogAutoScroll = true;
let expandedLogEntries = {};
let renderedLogEntries = {};

// Caching and state variables for performance optimization
let lastTasksListJson = null;
let lastFileTreeJson = null;
let expandedFolders = {};
let lastTaskDetailsJson = null;
let activeTaskStatus = null;
let lastRenderedStatus = null;

function isExecutionLogAtBottom() {
  const container = document.getElementById("execution-log");
  if (!container) return true;
  const threshold = 20;
  return (
    container.scrollHeight - container.scrollTop - container.clientHeight <=
    threshold
  );
}

// On Load
document.addEventListener("DOMContentLoaded", () => {
  refreshDashboard();
  loadTasksList();

  const logContainer = document.getElementById("execution-log");
  if (logContainer) {
    logContainer.addEventListener("scroll", () => {
      executionLogAutoScroll = isExecutionLogAtBottom();
    });
  }

  // Periodically refresh list & active task log
  setInterval(() => {
    loadTasksList();
    if (currentTaskId) {
      pollActiveTaskState();
    } else {
      refreshDashboard();
    }
  }, 3000);
});

// Load Task List Sidebar
async function loadTasksList() {
  try {
    const res = await fetch("/api/tasks");
    const tasks = await res.json();

    // Update activeTaskStatus first
    const activeTask = tasks.find((t) => t.task_id === currentTaskId);
    activeTaskStatus = activeTask ? activeTask.status : null;

    const tasksJson = JSON.stringify(tasks);
    const cacheKey = `${currentTaskId}|${tasksJson}`;
    if (cacheKey === lastTasksListJson) {
      return; // Skip DOM rebuild if task list and active task selection are unchanged
    }
    lastTasksListJson = cacheKey;

    const listEl = document.getElementById("tasks-list");
    listEl.innerHTML = "";

    if (tasks.length === 0) {
      listEl.innerHTML =
        '<div style="color: var(--text-muted); font-size: 13px; text-align: center; padding: 20px;">No tasks found</div>';
      return;
    }

    tasks.forEach((task) => {
      const isActive = task.task_id === currentTaskId;
      const item = document.createElement("div");
      item.className = `task-item ${isActive ? "active" : ""}`;
      item.onclick = () => selectTask(task.task_id);

      const statusClass = `status-${task.status}`;
      const statusLabel = task.status.replace(/_/g, " ");

      item.innerHTML = `
                <div class="task-item-header">
                    <span class="task-item-id">${task.task_id}</span>
                    <span class="task-item-status ${statusClass}">${statusLabel}</span>
                </div>
                <div class="task-item-desc" title="${task.task}">${task.task}</div>
                <div class="task-item-date">
                    <span>Step: ${task.step}</span>
                    <span>${task.created_at || ""}</span>
                </div>
            `;
      listEl.appendChild(item);
    });
  } catch (err) {
    console.error("Error loading tasks", err);
  }
}

// Refresh Stats Dashboard
async function refreshDashboard() {
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();

    document.getElementById("stat-total").innerText = data.stats.total_tasks;
    document.getElementById("stat-rate").innerText =
      data.stats.success_rate + "%";
    document.getElementById("stat-running").innerText = data.stats.running;
    document.getElementById("stat-lessons").innerText =
      data.stats.lessons_count;
  } catch (err) {
    console.error("Error refreshing dashboard", err);
  }
}

// Select task from sidebar
async function selectTask(taskId) {
  if (currentTaskId === taskId) {
    return; // Avoid reloading active task and duplicating logs
  }
  currentTaskId = taskId;
  renderedLogEntries = {};

  // Clear execution log container to prevent any UI mismatch
  const container = document.getElementById("execution-log");
  if (container) {
    container.innerHTML = "";
    container.dataset.taskId = "";
  }

  executionLogAutoScroll = true;
  lastTaskDetailsJson = null;
  lastFileTreeJson = null;
  expandedFolders = {}; // clear folders state when switching tasks
  closeEditor();
  toggleSidebar(false);

  document.getElementById("welcome-view").style.display = "none";
  document.getElementById("task-view").style.display = "flex";

  // Highlight list item
  const items = document.querySelectorAll(".task-item");
  items.forEach((it) => it.classList.remove("active"));

  // Force fetch details immediately
  await getTaskDetails(taskId);
  loadTasksList();
}

// Fetch task details from API
async function getTaskDetails(taskId) {
  try {
    const res = await fetch(`/api/tasks/${taskId}`);
    if (!res.ok) throw new Error();
    const task = await res.json();

    const detailsJson = JSON.stringify(task);
    if (detailsJson === lastTaskDetailsJson) {
      return;
    }
    lastTaskDetailsJson = detailsJson;
    lastRenderedStatus = task.status;

    // Update header info
    document.getElementById("active-task-desc").innerText = task.task;
    document.getElementById("active-task-desc").title = task.task;

    const statusEl = document.getElementById("active-task-status");
    statusEl.innerText = task.status.replace(/_/g, " ");
    statusEl.className = `task-header-badge status-${task.status}`;

    document.getElementById("active-task-step").innerText =
      `Step: ${task.step}`;

    const supervisorBanner = document.getElementById("supervision-banner");
    if (task.supervision_status && task.supervision_status !== "idle") {
      const bannerTitle = document.getElementById("supervision-title");
      const statusLabel = document.getElementById("supervision-status");
      const reasonLabel = document.getElementById("supervision-reason");
      const timestampLabel = document.getElementById("supervision-timestamp");
      const extraLabel = document.getElementById("supervision-extra");

      const statusText = task.supervision_status.replace(/_/g, " ").toUpperCase();
      statusLabel.innerText = statusText;
      statusLabel.className = `supervision-pill status-${task.supervision_status}`;

      if (task.supervision_status === "reroute") {
        bannerTitle.innerText = "Supervisor Rerouted the Next Step";
      } else if (task.supervision_status === "pause") {
        bannerTitle.innerText = "Supervisor Paused Execution";
      } else {
        bannerTitle.innerText = "Supervisor Approved the Action";
      }

      reasonLabel.innerText = task.supervision_reason || "No supervisor reasoning available.";
      timestampLabel.innerText = task.supervision_last_review
        ? `Reviewed: ${new Date(task.supervision_last_review).toLocaleString()}`
        : "";
      extraLabel.innerText =
        task.supervision_status === "reroute" && Array.isArray(task.steps)
          ? `New active step: ${task.steps[task.current_step_idx] || "(unknown)"}`
          : "";

      supervisorBanner.style.display = "grid";
    } else {
      supervisorBanner.style.display = "none";
    }

    // Render Execution logs
    renderExecutionLogs(task.execution_log);

    // Render Workspace Files
    renderFileTree(task.file_tree);

    // Handle Intervention Console
    const consoleEl = document.getElementById("intervention-console");
    if (
      task.status === "awaiting_intervention" ||
      task.status === "completed" ||
      task.status === "failed"
    ) {
      consoleEl.style.display = "flex";

      const proposed = task.proposed_tool;
      const thoughtEl = document.getElementById(
        "intervention-thought-container",
      );
      const proposedEl = document.getElementById("proposed-tool-container");

      if (proposed) {
        if (proposed.thought) {
          thoughtEl.style.display = "block";
          document.getElementById("intervention-thought").innerText =
            proposed.thought;
        } else {
          thoughtEl.style.display = "none";
        }

        if (proposed.name) {
          proposedEl.style.display = "block";
          document.getElementById("proposed-tool-name").innerText =
            proposed.name;
          document.getElementById("proposed-tool-args").value = JSON.stringify(
            proposed.args,
            null,
            2,
          );

          const approveBtn = document.getElementById("btn-approve-tool");
          approveBtn.innerText = "Approve & Step";
          approveBtn.style.display = "flex";
          document.getElementById("btn-modify-tool").style.display = "flex";
        } else if (proposed.thought) {
          // A plan-only response: let user continue to next execution turn
          proposedEl.style.display = "none";
          const approveBtn = document.getElementById("btn-approve-tool");
          approveBtn.innerText = "Continue";
          approveBtn.style.display = "flex";
          document.getElementById("btn-modify-tool").style.display = "none";
        } else {
          // Formatting error or system prompt turn
          proposedEl.style.display = "none";
          document.getElementById("btn-approve-tool").style.display = "none";
          document.getElementById("btn-modify-tool").style.display = "none";
        }
      } else {
        thoughtEl.style.display = "none";
        proposedEl.style.display = "none";
        document.getElementById("btn-approve-tool").style.display = "none";
        document.getElementById("btn-modify-tool").style.display = "none";
      }
    } else {
      consoleEl.style.display = "none";
    }
  } catch (err) {
    console.error("Error loading task details", err);
    currentTaskId = null;
    lastTaskDetailsJson = null;
    lastFileTreeJson = null;
    document.getElementById("welcome-view").style.display = "flex";
    document.getElementById("task-view").style.display = "none";
  }
}

// Active task polling during execution
async function pollActiveTaskState() {
  if (!currentTaskId) return;
  // Poll if the task is actively running, or if we haven't loaded it, or if the status in the sidebar differs from what we last rendered
  const statusNeedsPoll =
    activeTaskStatus === "running" ||
    activeTaskStatus === "processando" ||
    activeTaskStatus !== lastRenderedStatus ||
    !lastTaskDetailsJson;
  if (statusNeedsPoll) {
    await getTaskDetails(currentTaskId);
  }
}

// Render logs
function escapeHtml(text) {
  if (text === null || text === undefined) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderCollapsibleText(text) {
  return `<div class="log-collapsible-text">${text}</div>`;
}

function formatOllamaUsage(usage) {
  if (!usage || typeof usage !== "object") return "";
  const parts = [];
  if (Number.isInteger(usage.prompt_tokens)) {
    parts.push(`Prompt: ${usage.prompt_tokens}`);
  }
  if (Number.isInteger(usage.completion_tokens)) {
    parts.push(`Completion: ${usage.completion_tokens}`);
  }
  if (Number.isInteger(usage.total_tokens)) {
    parts.push(`Total: ${usage.total_tokens}`);
  }
  if (usage.tokens_per_second) {
    parts.push(`Speed: ${usage.tokens_per_second} t/s`);
  }
  if (!parts.length && usage.tokens && Number.isInteger(usage.tokens)) {
    parts.push(`Total: ${usage.tokens}`);
  }
  return parts.length ? `Ollama: ${parts.join(" | ")}` : "";
}

function stripHtmlTags(text) {
  return text.replace(/<[^>]+>/g, "");
}

function getLogEntryKey(entry) {
  const rawContent = entry.content || "";
  const stepVal = (entry.step !== undefined && entry.step !== null) ? entry.step : "";
  return `${entry.role || ""}|${stepVal}|${rawContent.slice(0, 200)}`;
}

function renderCardBody(entry) {
  const rawContent = entry.content || "";
  const contentHtml = renderLogContent(entry);
  const entryKey = getLogEntryKey(entry);
  const isExpanded = Boolean(expandedLogEntries[entryKey]);

  if (rawContent.length <= 300) {
    return contentHtml;
  }

  const previewText = stripHtmlTags(rawContent).slice(0, 300);
  const preview = `${escapeHtml(previewText)}...`;
  return `
    <div class="log-collapsible-card">
      <div class="log-collapsible-preview" style="display: ${isExpanded ? "none" : "block"};">${preview}</div>
      <button type="button" class="log-expand-btn" onclick="toggleLogExpand(this)" data-expanded="${isExpanded}" data-entry-key="${encodeURIComponent(entryKey)}">${isExpanded ? "Recolher" : "Expandir"}</button>
      <div class="log-collapsible-full" style="display: ${isExpanded ? "block" : "none"};">${contentHtml}</div>
    </div>
  `;
}

function toggleLogExpand(button) {
  const container = button.closest(".log-collapsible-card");
  if (!container) return;

  const preview = container.querySelector(".log-collapsible-preview");
  const full = container.querySelector(".log-collapsible-full");
  const entryKey = decodeURIComponent(button.dataset.entryKey || "");
  const expanded = button.dataset.expanded === "true";

  if (expanded) {
    preview.style.display = "block";
    full.style.display = "none";
    button.innerText = "Expandir";
    button.dataset.expanded = "false";
    if (entryKey) delete expandedLogEntries[entryKey];
  } else {
    preview.style.display = "none";
    full.style.display = "block";
    button.innerText = "Recolher";
    button.dataset.expanded = "true";
    if (entryKey) expandedLogEntries[entryKey] = true;
  }
}

function renderExecutionLogs(log) {
  const container = document.getElementById("execution-log");
  if (!container) return;
  if (!Array.isArray(log)) log = [];

  if (container.dataset.taskId !== currentTaskId) {
    renderedLogEntries = {};
    container.dataset.taskId = currentTaskId || "";
    container.innerHTML = "";
  }

  const preserveScrollTop = container.scrollTop;

  log.forEach((entry) => {
    const entryKey = getLogEntryKey(entry);
    if (renderedLogEntries[entryKey]) return;
    renderedLogEntries[entryKey] = true;

    const card = document.createElement("div");
    card.className = `log-card log-role-${entry.role}`;

    const titleRole = entry.role.replace(/_/g, " ").toUpperCase();
    let icon = '<i class="fa-solid fa-server"></i>';
    if (entry.role === "assistant") icon = '<i class="fa-solid fa-robot"></i>';
    if (entry.role === "tool_result")
      icon = '<i class="fa-solid fa-terminal"></i>';
    if (entry.role === "user_intervention")
      icon = '<i class="fa-solid fa-user-pen"></i>';

    const usageBadge = entry.ollama_usage
      ? `<span class="log-usage-badge">${escapeHtml(formatOllamaUsage(entry.ollama_usage))}</span>`
      : "";

    card.innerHTML = `
            <div class="log-card-header">
                <span>${icon} ${titleRole} (Step ${(entry.step !== undefined && entry.step !== null) ? entry.step : "-"})</span>
                ${usageBadge}
            </div>
            <div class="log-card-body">
                ${renderCardBody(entry)}
            </div>
        `;
    container.appendChild(card);
  });

  if (executionLogAutoScroll) {
    container.scrollTop = container.scrollHeight;
  } else {
    container.scrollTop = preserveScrollTop;
  }
}

function renderLogContent(entry) {
  const rawContent = entry.content || "";
  const content = escapeHtml(rawContent);

  if (entry.role === "assistant") {
    let thoughtHtml = "";
    let toolHtml = "";

    const thoughtMatch =
      rawContent.match(/<thought>([\s\S]*?)<\/thought>/i) ||
      rawContent.match(/<thought>([\s\S]*?)(?:<tool|\Z)/i);
    if (thoughtMatch) {
      thoughtHtml = `<div class="log-thought">${renderCollapsibleText(
        escapeHtml(thoughtMatch[1].trim()),
      )}</div>`;
    }

    const toolMatch = rawContent.match(
      /<tool\s+name=["']([^"']+)["']\s*>([\s\S]*?)<\/tool>/i,
    );
    if (toolMatch) {
      const toolName = toolMatch[1].trim();
      const argsBlock = escapeHtml(toolMatch[2].trim());

      toolHtml = `
                <div class="log-tool-call">
                    <div class="log-tool-title"><i class="fa-solid fa-wrench"></i> Tool Action: ${escapeHtml(toolName)}</div>
                    <div class="log-tool-args">${renderCollapsibleText(argsBlock)}</div>
                </div>
            `;
    }

    if (!thoughtHtml && !toolHtml) {
      return `<div class="log-thought">${renderCollapsibleText(content)}</div>`;
    }

    return thoughtHtml + toolHtml;
  }

  if (entry.role === "tool_result") {
    return `<div class="log-thought log-tool-result-text">${renderCollapsibleText(content)}</div>`;
  }

  return `<div style="font-size: 14px; line-height: 1.5;">${renderCollapsibleText(content)}</div>`;
}

// Render Workspace File Tree
function renderFileTree(nodes) {
  const fileTreeJson = JSON.stringify(nodes);
  if (fileTreeJson === lastFileTreeJson) {
    return; // File tree hasn't changed, skip rebuilding DOM
  }
  lastFileTreeJson = fileTreeJson;

  const container = document.getElementById("file-tree");
  container.innerHTML = "";

  if (!nodes || nodes.length === 0) {
    container.innerHTML =
      '<div style="color: var(--text-muted); font-size: 12px; padding: 10px;">(Empty Workspace)</div>';
    return;
  }

  container.appendChild(buildTreeNodeList(nodes));
}

function buildTreeNodeList(nodes) {
  const ul = document.createElement("div");
  ul.className = "tree-children";

  nodes.forEach((node) => {
    const li = document.createElement("div");
    li.className = "tree-node";

    const isDir = node.type === "directory";

    if (isDir) {
      const isExpanded = !!expandedFolders[node.path];
      const folderIconClass = isExpanded
        ? "fa-solid fa-folder-open tree-icon-folder"
        : "fa-solid fa-folder tree-icon-folder";

      const item = document.createElement("div");
      item.className = `tree-item ${editingFilePath === node.path ? "active" : ""}`;
      item.innerHTML = `<i class="${folderIconClass}"></i> <span>${node.name}</span>`;

      const subUl = buildTreeNodeList(node.children);
      subUl.style.display = isExpanded ? "block" : "none";

      item.onclick = (e) => {
        e.stopPropagation();
        const currentlyExpanded = expandedFolders[node.path];
        if (currentlyExpanded) {
          expandedFolders[node.path] = false;
          subUl.style.display = "none";
          item.querySelector(".tree-icon-folder").className =
            "fa-solid fa-folder tree-icon-folder";
        } else {
          expandedFolders[node.path] = true;
          subUl.style.display = "block";
          item.querySelector(".tree-icon-folder").className =
            "fa-solid fa-folder-open tree-icon-folder";
        }
      };

      li.appendChild(item);
      li.appendChild(subUl);
    } else {
      const item = document.createElement("div");
      item.className = `tree-item ${editingFilePath === node.path ? "active" : ""}`;
      item.innerHTML = `<i class="fa-solid fa-file-code tree-icon-file"></i> <span>${node.name}</span>`;
      item.onclick = (e) => {
        e.stopPropagation();
        openFileEditor(node.path);
      };
      li.appendChild(item);
    }

    ul.appendChild(li);
  });

  return ul;
}

// Open file in Editor panel
async function openFileEditor(filePath) {
  editingFilePath = filePath;
  document.getElementById("editor-pane").style.display = "flex";
  document.getElementById("editor-filename").innerText = filePath
    .split("/")
    .pop();

  // Update active styling in file tree
  const treeItems = document.querySelectorAll(".tree-item");
  treeItems.forEach((el) => {
    if (el.textContent.trim() === filePath.split("/").pop()) {
      el.classList.add("active");
    } else {
      el.classList.remove("active");
    }
  });

  // Reset tab behavior and preview iframe
  const isHtml = filePath.toLowerCase().endsWith(".html") || filePath.toLowerCase().endsWith(".htm");
  const tabsContainer = document.getElementById("editor-tabs");
  if (isHtml) {
    tabsContainer.style.display = "flex";
  } else {
    tabsContainer.style.display = "none";
  }

  // Default to code tab
  switchEditorTab('code');

  try {
    const res = await fetch(
      `/api/tasks/${currentTaskId}/files/view?path=${encodeURIComponent(filePath)}`,
    );
    const data = await res.json();
    document.getElementById("editor-textarea").value = data.content || "";
  } catch (err) {
    console.error("Error viewing file", err);
  }
}

// Close File Editor panel
function closeEditor() {
  editingFilePath = null;
  
  // Reset maximized state
  const editorPane = document.getElementById("editor-pane");
  editorPane.style.display = "none";
  editorPane.classList.remove("maximized");
  
  // Reset toggle size button icon
  const toggleBtn = document.getElementById("btn-toggle-size");
  if (toggleBtn) {
    toggleBtn.innerHTML = '<i class="fa-solid fa-angles-up"></i>';
  }

  document.getElementById("editor-textarea").value = "";
  
  const iframe = document.getElementById("editor-preview");
  if (iframe) {
    iframe.src = "about:blank";
  }

  const treeItems = document.querySelectorAll(".tree-item");
  treeItems.forEach((el) => el.classList.remove("active"));
}

// Tab Switching logic
function switchEditorTab(tab) {
  const codeTab = document.getElementById("tab-code");
  const previewTab = document.getElementById("tab-preview");
  const textarea = document.getElementById("editor-textarea");
  const iframe = document.getElementById("editor-preview");
  const saveBtn = document.getElementById("btn-save-code");
  const fsBtn = document.getElementById("btn-fullscreen-preview");
  const openBtn = document.getElementById("btn-new-tab-preview");

  if (tab === "preview") {
    codeTab.classList.remove("active");
    previewTab.classList.add("active");
    textarea.style.display = "none";
    iframe.style.display = "block";
    saveBtn.style.display = "none";
    fsBtn.style.display = "flex";
    openBtn.style.display = "flex";

    // Set src to the new raw endpoint to reload page
    if (currentTaskId && editingFilePath) {
      iframe.src = `/api/tasks/${currentTaskId}/files/raw/${editingFilePath}`;
    }
  } else {
    codeTab.classList.add("active");
    previewTab.classList.remove("active");
    textarea.style.display = "block";
    iframe.style.display = "none";
    saveBtn.style.display = "flex";
    fsBtn.style.display = "none";
    openBtn.style.display = "none";
  }
}

// Toggle Editor Height inside the workspace column
function toggleEditorSize() {
  const editorPane = document.getElementById("editor-pane");
  const toggleBtn = document.getElementById("btn-toggle-size");
  if (!editorPane || !toggleBtn) return;

  const isMaximized = editorPane.classList.toggle("maximized");
  if (isMaximized) {
    toggleBtn.innerHTML = '<i class="fa-solid fa-angles-down"></i>';
  } else {
    toggleBtn.innerHTML = '<i class="fa-solid fa-angles-up"></i>';
  }
}

// Fullscreen Iframe Preview (standard browser Fullscreen API)
function fullscreenPreview() {
  const iframe = document.getElementById("editor-preview");
  if (!iframe) return;

  if (iframe.requestFullscreen) {
    iframe.requestFullscreen();
  } else if (iframe.webkitRequestFullscreen) { /* Safari */
    iframe.webkitRequestFullscreen();
  } else if (iframe.msRequestFullscreen) { /* IE11 */
    iframe.msRequestFullscreen();
  }
}

// Open HTML file in standalone new browser tab
function openPreviewInNewTab() {
  if (currentTaskId && editingFilePath) {
    window.open(`/api/tasks/${currentTaskId}/files/raw/${editingFilePath}`, '_blank');
  }
}

// Save file edit content
async function saveEditorContent() {
  if (!currentTaskId || !editingFilePath) return;
  const content = document.getElementById("editor-textarea").value;

  try {
    const res = await fetch(`/api/tasks/${currentTaskId}/files/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: editingFilePath, content: content }),
    });

    if (res.ok) {
      alert("File saved successfully!");
      // Refresh details to update file tree (if structure changed)
      getTaskDetails(currentTaskId);
    } else {
      alert("Failed to save file.");
    }
  } catch (err) {
    console.error("Error saving file", err);
  }
}

// Delete active task
async function deleteActiveTask() {
  if (!currentTaskId) return;
  if (
    !confirm(
      "Are you sure you want to delete this task? All workspace files and logs will be permanently removed.",
    )
  )
    return;

  try {
    const res = await fetch(`/api/tasks/${currentTaskId}`, {
      method: "DELETE",
    });
    if (res.ok) {
      currentTaskId = null;
      document.getElementById("welcome-view").style.display = "flex";
      document.getElementById("task-view").style.display = "none";
      loadTasksList();
      refreshDashboard();
    } else {
      alert("Failed to delete task.");
    }
  } catch (err) {
    console.error(err);
  }
}

// Submit Intervention
async function submitIntervention(action) {
  if (!currentTaskId) return;

  const payload = { action: action };

  if (action === "modify") {
    const toolName = document.getElementById("proposed-tool-name").innerText;
    let toolArgs = {};
    try {
      toolArgs = JSON.parse(
        document.getElementById("proposed-tool-args").value,
      );
    } catch (e) {
      alert("Invalid JSON format in arguments.");
      return;
    }
    payload.modified_tool = { name: toolName, args: toolArgs };
  }

  if (action === "inject") {
    const userPrompt = document
      .getElementById("intervention-prompt")
      .value.trim();
    if (!userPrompt) {
      alert("Please write a instruction prompt first.");
      return;
    }
    payload.user_prompt = userPrompt;
  }

  // Clear prompt only after a user-inject action so typed instructions are not lost during approve/modify actions.
  if (action === "inject") {
    document.getElementById("intervention-prompt").value = "";
  }

  try {
    // Show loading indicator
    const consoleEl = document.getElementById("intervention-console");
    consoleEl.style.opacity = "0.5";
    consoleEl.style.pointerEvents = "none";

    const res = await fetch(`/api/tasks/${currentTaskId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const task = await res.json();

    consoleEl.style.opacity = "1";
    consoleEl.style.pointerEvents = "all";

    getTaskDetails(currentTaskId);
    loadTasksList();
  } catch (err) {
    console.error(err);
  }
}

// --- Modals Handlers ---

function openNewTaskModal() {
  document.getElementById("modal-new-task").classList.add("active");
  document.getElementById("new-task-prompt").focus();
}

async function submitNewTask() {
  const taskText = document.getElementById("new-task-prompt").value.trim();
  if (!taskText) {
    alert("Please write a task description.");
    return;
  }
  const mode = document.getElementById("new-task-mode").value;
  const modelThink = document.getElementById("new-task-model-think").checked;

  closeModals();

  try {
    const res = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: taskText, mode: mode, model_think: modelThink }),
    });
    const task = await res.json();

    // Clear fields
    document.getElementById("new-task-prompt").value = "";
    document.getElementById("new-task-model-think").checked = true;

    // Select and load the new task
    selectTask(task.task_id);
  } catch (err) {
    console.error("Error creating task", err);
  }
}

// System Prompt Modal
async function openPromptModal() {
  try {
    const res = await fetch("/api/memory/prompt");
    const data = await res.json();
    document.getElementById("system-prompt-text").value = data.prompt || "";
    document.getElementById("modal-system-prompt").classList.add("active");
  } catch (err) {
    console.error(err);
  }
}

async function saveSystemPrompt() {
  const text = document.getElementById("system-prompt-text").value;
  try {
    const res = await fetch("/api/memory/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: text }),
    });
    if (res.ok) {
      alert("System prompt updated!");
      closeModals();
    } else {
      alert("Failed to update system prompt.");
    }
  } catch (err) {
    console.error(err);
  }
}

// Lessons learned Modal
async function openLessonsModal() {
  try {
    const res = await fetch("/api/memory/lessons");
    const data = await res.json();

    const container = document.getElementById("lessons-list-container");
    container.innerHTML = "";

    const lessons = data.lessons || [];
    if (lessons.length === 0) {
      container.innerHTML =
        '<div style="color: var(--text-muted); font-size: 13px; text-align: center;">No lessons learned yet. Complete tasks to gather learnings.</div>';
    } else {
      lessons.forEach((l, i) => {
        const item = document.createElement("div");
        item.style.background = "rgba(0,0,0,0.2)";
        item.style.padding = "16px";
        item.style.borderRadius = "8px";
        item.style.border = "1px solid var(--border-color)";
        item.style.marginBottom = "10px";

        item.innerHTML = `
                            <div style="font-weight: 700; color: #818cf8; margin-bottom: 6px;">Lesson ${i + 1}: ${l.title}</div>
                            ${l.error ? `<div style="font-family: var(--font-code); font-size: 12px; color: var(--color-danger); background: rgba(239, 68, 68, 0.05); padding: 8px; border-radius: 4px; margin-bottom: 6px;">Error: ${l.error}</div>` : ""}
                            <div style="font-size: 13px; color: var(--text-primary); line-height: 1.4;"><strong style="color: var(--color-success)">Fix:</strong> ${l.resolution}</div>
                        `;
        container.appendChild(item);
      });
    }

    document.getElementById("modal-lessons").classList.add("active");
  } catch (err) {
    console.error(err);
  }
}

function closeModals() {
  document
    .querySelectorAll(".modal-overlay")
    .forEach((el) => el.classList.remove("active"));
}

function toggleSidebar(open) {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");
  if (!sidebar || !overlay) return;

  if (open) {
    sidebar.classList.add("open");
    overlay.classList.add("active");
  } else {
    sidebar.classList.remove("open");
    overlay.classList.remove("active");
  }
}
