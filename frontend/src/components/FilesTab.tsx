interface CreatedFile {
  path: string;
  created_at: string;
  step?: number;
}

interface ToCreateFile {
  path: string;
}

export default function FilesTab({
  files,
  toCreateFiles = [],
  filesProgress = 0,
}: {
  files: CreatedFile[];
  toCreateFiles?: ToCreateFile[];
  filesProgress?: number;
}) {
  const createdSet = new Set(files.map(f => f.path));

  const hasAnyFiles = files.length > 0 || toCreateFiles.length > 0;

  if (!hasAnyFiles) {
    return (
      <div className="streaming-empty-state" id="created-empty">
        <i className="fa-solid fa-file-code"></i>
        <p>Files will appear here as the agent generates them</p>
      </div>
    );
  }

  return (
    <div className="files-panel" id="files-panel">
      {toCreateFiles.length > 0 && (
        <div className="files-progress-bar-container">
          <div className="files-progress-header">
            <span>Progress</span>
            <span className="files-progress-text">{files.length} / {toCreateFiles.length} files</span>
          </div>
          <div className="files-progress-bar">
            <div
              className="files-progress-fill"
              style={{ width: `${Math.min(filesProgress, 100)}%` }}
            />
          </div>
        </div>
      )}
      <div className="files-section">
        <div className="files-section-header">
          <i className="fa-solid fa-check-circle"></i>
          <span>Created</span>
          <span className="files-count" id="created-count">{files.length}</span>
        </div>
        <div className="files-section-body" id="created-list">
          {files.length === 0 ? (
            <div className="files-section-empty">No files created yet</div>
          ) : (
            files.map((file, idx) => (
              <div key={idx} className="created-file-item">
                <i className="fa-solid fa-file-code created-file-icon"></i>
                <span className="created-file-path" title={file.path}>{file.path}</span>
                {file.step ? <span className="created-file-meta">Step {file.step}</span> : null}
              </div>
            ))
          )}
        </div>
      </div>
      <div className="files-section">
        <div className="files-section-header">
          <i className="fa-solid fa-clock"></i>
          <span>To Create</span>
          <span className="files-count" id="tocreate-count">
            {toCreateFiles.length > 0
              ? toCreateFiles.length - files.filter(f => toCreateFiles.some(t => t.path === f.path)).length
              : 0}
          </span>
        </div>
        <div className="files-section-body" id="tocreate-list">
          {toCreateFiles.length === 0 ? (
            <div className="files-section-empty">No pending files to create</div>
          ) : (
            toCreateFiles.map((file, idx) => {
              const isCreated = createdSet.has(file.path);
              return (
                <div
                  key={idx}
                  className={`created-file-item${isCreated ? ' file-created' : ''}`}
                >
                  <i className={`fa-solid ${isCreated ? 'fa-check-circle' : 'fa-file-code'} created-file-icon`}></i>
                  <span className={`created-file-path${isCreated ? ' file-created-text' : ''}`} title={file.path}>
                    {file.path}
                  </span>
                  {isCreated && <span className="created-file-meta">Done</span>}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
