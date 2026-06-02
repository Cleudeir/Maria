import { useApp } from '../context/AppContext';
import type { FileTreeNode } from '../types';
import SupervisionBanner from './SupervisionBanner';
import FileTree from './FileTree';
import Editor from './Editor';

export default function WorkspaceTab({ taskId, fileTree }: { taskId: string; fileTree?: FileTreeNode[] }) {
  const { currentTask } = useApp();

  return (
    <div className="workspace-body">
      <div className="workspace-left">
        <div className="workspace-header">
          <span>Workspace Files</span>
          <button className="btn-open-folder" id="btn-open-folder" title="Open folder in file explorer"
            onClick={() => window.open(`http://192.168.20.180:10002/tasks/${taskId}/output/`, '_blank')}>
            <i className="fa-solid fa-folder-open"></i>
          </button>
        </div>
        {currentTask ? <SupervisionBanner task={currentTask} /> : null}
        <FileTree nodes={fileTree} taskId={taskId} />
      </div>
      <Editor taskId={taskId} />
    </div>
  );
}
