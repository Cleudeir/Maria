export default function StreamingTab({ isStreaming, content }: { isStreaming: boolean; content?: string }) {
  if (!isStreaming) {
    return (
      <div className="streaming-empty-state" id="streaming-empty">
        <i className="fa-solid fa-bolt"></i>
        <p>Streaming will appear when the agent is generating a response</p>
      </div>
    );
  }

  let text = content ?? 'Waiting for generation...';
  if (text.length > 200) {
    text = '...' + text.slice(-200);
  }

  return (
    <div className="streaming-panel" id="streaming-panel">
      <div className="streaming-header">
        <i className="fa-solid fa-circle-notch fa-spin"></i>
        <span>Generating response (last 200 chars shown)</span>
      </div>
      <div className="streaming-body" id="streaming-content">
        {text.split('\n').map((line, i) => <span key={i}>{line}<br /></span>)}
      </div>
    </div>
  );
}
