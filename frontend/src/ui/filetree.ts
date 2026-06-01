import type { FileTreeNode } from '../types';
import { getState } from '../state/store';
import { $, el } from '../utils/dom';
import { openFileEditor } from './editor';

let lastTreeJson = '';

export function initOpenFolderButton(): void {
  $('#btn-open-folder')?.addEventListener('click', () => {
    const currentTaskId = getState('currentTaskId');
    if (!currentTaskId) return;
    window.open(`http://192.168.20.180:10002/tasks/${currentTaskId}/output/`, '_blank');
  });
}

function buildNodeList(nodes: FileTreeNode[]): HTMLElement {
  const container = el('div', { className: 'tree-children' });
  const editingPath = getState('editingFilePath');

  for (const node of nodes) {
    const li = el('div', { className: 'tree-node' });
    const isDir = node.type === 'directory';

    if (isDir) {
      const isExpanded = getState('expandedFolders').has(node.path);
      const iconClass = isExpanded
        ? 'fa-solid fa-folder-open tree-icon-folder'
        : 'fa-solid fa-folder tree-icon-folder';

      const item = el('div', {
        className: `tree-item${editingPath === node.path ? ' active' : ''}`,
      });
      item.innerHTML = `<i class="${iconClass}"></i> <span>${node.name}</span>`;

      const subList = buildNodeList(node.children ?? []);
      subList.style.display = isExpanded ? 'block' : 'none';

      item.addEventListener('click', (e) => {
        e.stopPropagation();
        const folders = getState('expandedFolders');
        if (folders.has(node.path)) {
          folders.delete(node.path);
          subList.style.display = 'none';
          const icon = item.querySelector('.tree-icon-folder');
          if (icon) icon.className = 'fa-solid fa-folder tree-icon-folder';
        } else {
          folders.add(node.path);
          subList.style.display = 'block';
          const icon = item.querySelector('.tree-icon-folder');
          if (icon) icon.className = 'fa-solid fa-folder-open tree-icon-folder';
        }
      });

      li.appendChild(item);
      li.appendChild(subList);
    } else {
      const item = el('div', {
        className: `tree-item${editingPath === node.path ? ' active' : ''}`,
      });
      item.innerHTML = `<i class="fa-solid fa-file-code tree-icon-file"></i> <span>${node.name}</span>`;

      item.addEventListener('click', (e) => {
        e.stopPropagation();
        openFileEditor(node.path);
      });

      li.appendChild(item);
    }

    container.appendChild(li);
  }

  return container;
}

export function renderFileTree(nodes?: FileTreeNode[]): void {
  const container = $('#file-tree');
  if (!container) return;

  const json = JSON.stringify(nodes);
  if (json === lastTreeJson) return;
  lastTreeJson = json;

  if (!nodes?.length) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 10px;">(Empty Workspace)</div>';
    return;
  }

  container.innerHTML = '';
  container.appendChild(buildNodeList(nodes));
}
