export default function StreamingTab({ isStreaming, content }: { isStreaming: boolean; content?: string }) {
  if (!isStreaming) {
    return (
      <div className="streaming-empty-state" id="streaming-empty">
        <i className="fa-solid fa-bolt"></i>
        <p>Streaming will appear when the agent is generating a response</p>
      </div>
    );
  }

  const text = content ?? 'Waiting for generation...';

  return (
    <div className="streaming-panel" id="streaming-panel">
      <div className="streaming-header">
        <i className="fa-solid fa-circle-notch fa-spin"></i>
        <span>Generating response</span>
      </div>
      <div className="streaming-body" id="streaming-content">
        {text.split('\n').map((line, i) => <span key={i}>{line}<br /></span>)}
      </div>
    </div>
  );
}
