import { useState, useEffect, useRef } from 'react';
import type { EditorTab } from '../types';
import { useApp } from '../context/AppContext';
import { api } from '../api/client';

export default function Editor({ taskId }: { taskId: string }) {
  const { editingFilePath, editorTab, setEditorTab, closeEditor: close } = useApp();
  const [maximized, setMaximized] = useState(false);
  const [content, setContent] = useState('');
  const contentLoadedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!editingFilePath) return;
    if (contentLoadedRef.current === editingFilePath) return;
    api.viewFile(taskId, editingFilePath)
      .then(data => { setContent(data.content ?? ''); contentLoadedRef.current = editingFilePath; })
      .catch(() => { setContent(''); contentLoadedRef.current = editingFilePath; });
  }, [editingFilePath, taskId]);

  const isHtml = editingFilePath?.toLowerCase().endsWith('.html') || editingFilePath?.toLowerCase().endsWith('.htm');
  const showTabs = isHtml;

  const saveFile = async () => {
    if (!editingFilePath) return;
    try {
      await api.editFile(taskId, editingFilePath, content);
      alert('File saved successfully!');
    } catch {
      alert('Failed to save file.');
    }
  };

  if (!editingFilePath) return null;

  return (
    <div className={`editor-container${maximized ? ' maximized' : ''}`} id="editor-pane">
      <div className="editor-header">
        <div className="editor-header-left">
          <span className="editor-filename" id="editor-filename">{editingFilePath.split('/').pop()}</span>
          {showTabs ? (
            <div className="editor-tabs" id="editor-tabs">
              <button className={`btn-editor${editorTab === 'code' ? ' active' : ''}`} onClick={() => setEditorTab('code')}>Code</button>
              <button className={`btn-editor${editorTab === 'preview' ? ' active' : ''}`} onClick={() => setEditorTab('preview')}>Preview</button>
            </div>
          ) : null}
        </div>
        <div className="editor-actions">
          <button className="btn-editor" onClick={() => setMaximized(prev => !prev)} title="Maximize / Minimize">
            <i className={`fa-solid ${maximized ? 'fa-angles-down' : 'fa-angles-up'}`}></i>
          </button>
          {editorTab === 'preview' ? (
            <>
              <button className="btn-editor" id="btn-fullscreen-preview" style={{ display: 'inline-flex' }}
                onClick={() => {
                  const iframe = document.getElementById('editor-preview') as HTMLIFrameElement;
                  if (iframe?.requestFullscreen) iframe.requestFullscreen();
                }}>
                <i className="fa-solid fa-maximize"></i> Fullscreen
              </button>
              <button className="btn-editor" id="btn-new-tab-preview" style={{ display: 'inline-flex' }}
                onClick={() => window.open(`/api/tasks/${taskId}/files/raw/${editingFilePath}`, '_blank')}>
                <i className="fa-solid fa-up-right-from-square"></i> Open
              </button>
            </>
          ) : null}
          <button className="btn-editor" onClick={close}>Cancel</button>
          <button className="btn-editor btn-editor-save" onClick={saveFile}>Save</button>
        </div>
      </div>
      <textarea
        className="editor-textarea"
        id="editor-textarea"
        spellCheck={false}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        style={{ display: editorTab === 'code' ? 'block' : 'none' }}
      />
      {editorTab === 'preview' && editingFilePath ? (
        <iframe
          className="editor-preview"
          id="editor-preview"
          src={`/api/tasks/${taskId}/files/raw/${editingFilePath}`}
          sandbox="allow-scripts"
          style={{ display: 'block' }}
        />
      ) : null}
    </div>
  );
}
