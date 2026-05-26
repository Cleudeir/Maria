import type { EditorTab } from '../types';
import { getState, setState } from '../state/store';
import { $, hide, show, toggleClass } from '../utils/dom';
import { api } from '../api/client';

export async function openFileEditor(filePath: string): Promise<void> {
  const taskId = getState('currentTaskId');
  if (!taskId) return;

  setState('editingFilePath', filePath);
  const pane = $('#editor-pane');
  const filename = $('#editor-filename');
  const textarea = $('#editor-textarea') as HTMLTextAreaElement | null;

  show(pane, 'flex');
  if (filename) filename.textContent = filePath.split('/').pop() ?? '';

  const isHtml = filePath.toLowerCase().endsWith('.html') || filePath.toLowerCase().endsWith('.htm');
  const tabs = $('#editor-tabs');
  if (tabs) tabs.style.display = isHtml ? 'flex' : 'none';

  switchEditorTab('code');

  try {
    const data = await api.viewFile(taskId, filePath);
    if (textarea) textarea.value = data.content ?? '';
  } catch (err) {
    console.error('Error viewing file', err);
  }

  updateTreeActiveState(filePath);
}

export function closeEditor(): void {
  setState('editingFilePath', null);
  setState('editorTab', 'code');

  const pane = $('#editor-pane');
  if (pane) {
    hide(pane);
    pane.classList.remove('maximized');
  }

  const toggleBtn = $('#btn-toggle-size');
  if (toggleBtn) toggleBtn.innerHTML = '<i class="fa-solid fa-angles-up"></i>';

  const textarea = $('#editor-textarea') as HTMLTextAreaElement | null;
  if (textarea) textarea.value = '';

  const iframe = $('#editor-preview') as HTMLIFrameElement | null;
  if (iframe) iframe.src = 'about:blank';

  updateTreeActiveState(null);
}

export function switchEditorTab(tab: EditorTab): void {
  setState('editorTab', tab);

  const codeTab = $('#tab-code');
  const previewTab = $('#tab-preview');
  const textarea = $('#editor-textarea');
  const iframe = $('#editor-preview') as HTMLIFrameElement | null;
  const saveBtn = $('#btn-save-code');
  const fsBtn = $('#btn-fullscreen-preview');
  const openBtn = $('#btn-new-tab-preview');

  if (tab === 'preview') {
    toggleClass(codeTab, 'active', false);
    toggleClass(previewTab, 'active', true);
    if (textarea) textarea.style.display = 'none';
    if (iframe) {
      iframe.style.display = 'block';
      const taskId = getState('currentTaskId');
      const filePath = getState('editingFilePath');
      if (taskId && filePath) {
        iframe.src = `/api/tasks/${taskId}/files/raw/${filePath}`;
      }
    }
    hide(saveBtn);
    show(fsBtn, 'flex');
    show(openBtn, 'flex');
  } else {
    toggleClass(codeTab, 'active', true);
    toggleClass(previewTab, 'active', false);
    if (textarea) textarea.style.display = 'block';
    if (iframe) iframe.style.display = 'none';
    show(saveBtn, 'flex');
    hide(fsBtn);
    hide(openBtn);
  }
}

export function toggleEditorSize(): void {
  const pane = $('#editor-pane');
  const toggleBtn = $('#btn-toggle-size');
  if (!pane || !toggleBtn) return;

  const isMaximized = pane.classList.toggle('maximized');
  toggleBtn.innerHTML = isMaximized
    ? '<i class="fa-solid fa-angles-down"></i>'
    : '<i class="fa-solid fa-angles-up"></i>';
}

export function fullscreenPreview(): void {
  const iframe = $('#editor-preview') as HTMLIFrameElement | null;
  if (!iframe) return;

  if (iframe.requestFullscreen) iframe.requestFullscreen();
}

export function openPreviewInNewTab(): void {
  const taskId = getState('currentTaskId');
  const filePath = getState('editingFilePath');
  if (taskId && filePath) {
    window.open(`/api/tasks/${taskId}/files/raw/${filePath}`, '_blank');
  }
}

export async function saveEditorContent(): Promise<void> {
  const taskId = getState('currentTaskId');
  const filePath = getState('editingFilePath');
  const textarea = $('#editor-textarea') as HTMLTextAreaElement | null;
  if (!taskId || !filePath || !textarea) return;

  try {
    await api.editFile(taskId, filePath, textarea.value);
    alert('File saved successfully!');
  } catch (err) {
    console.error('Error saving file', err);
    alert('Failed to save file.');
  }
}

function updateTreeActiveState(activePath: string | null): void {
  document.querySelectorAll<HTMLElement>('.tree-item').forEach(el => {
    const span = el.querySelector('span');
    const isActive = activePath && span?.textContent === activePath.split('/').pop();
    el.classList.toggle('active', !!isActive);
  });
}

export function initEditor(): void {
  $('#btn-close-editor')?.addEventListener('click', closeEditor);
  $('#btn-save-code')?.addEventListener('click', saveEditorContent);
  $('#btn-toggle-size')?.addEventListener('click', toggleEditorSize);
  $('#btn-fullscreen-preview')?.addEventListener('click', fullscreenPreview);
  $('#btn-new-tab-preview')?.addEventListener('click', openPreviewInNewTab);
  $('#tab-code')?.addEventListener('click', () => switchEditorTab('code'));
  $('#tab-preview')?.addEventListener('click', () => switchEditorTab('preview'));
}
