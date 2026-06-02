import { useState } from 'react';
import type { FileTreeNode } from '../types';
import { useApp } from '../context/AppContext';

function FileNode({ node, taskId }: { node: FileTreeNode; taskId: string }) {
  const [expanded, setExpanded] = useState(false);
  const { editingFilePath, setEditingFilePath, setEditorTab } = useApp();

  if (node.type === 'directory') {
    return (
      <div className="tree-node">
        <div className={`tree-item${editingFilePath === node.path ? ' active' : ''}`} onClick={(e) => {
          e.stopPropagation();
          setExpanded(prev => !prev);
        }}>
          <i className={`fa-solid ${expanded ? 'fa-folder-open' : 'fa-folder'} tree-icon-folder`}></i>
          <span>{node.name}</span>
        </div>
        {expanded && node.children ? (
          <div className="tree-children" style={{ display: 'block' }}>
            {node.children.map((child, i) => (
              <FileNode key={i} node={child} taskId={taskId} />
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="tree-node">
      <div
        className={`tree-item${editingFilePath === node.path ? ' active' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          setEditingFilePath(node.path);
          setEditorTab('code');
        }}
      >
        <i className="fa-solid fa-file-code tree-icon-file"></i>
        <span>{node.name}</span>
      </div>
    </div>
  );
}

export default function FileTree({ nodes, taskId }: { nodes?: FileTreeNode[]; taskId?: string }) {
  if (!nodes?.length) {
    return (
      <div className="file-tree-container" id="file-tree">
        <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 10 }}>(Empty Workspace)</div>
      </div>
    );
  }

  return (
    <div className="file-tree-container" id="file-tree">
      {nodes.map((node, i) => (
        <div key={i} className="tree-children" style={{ display: 'block' }}>
          <FileNode node={node} taskId={taskId ?? ""} />
        </div>
      ))}
    </div>
  );
}
