export default function MobileTopbar() {
  return (
    <div className="mobile-topbar">
      <button className="btn-hamburger" id="btn-hamburger" aria-label="Open sidebar" onClick={() => {
        document.getElementById('sidebar')?.classList.add('open');
        document.getElementById('sidebar-overlay')?.classList.add('active');
      }}>
        <i className="fa-solid fa-bars"></i>
      </button>
      <div className="brand">
        <div className="brand-logo"><i className="fa-solid fa-brain-circuit"></i> AGENTIC</div>
        <div className="brand-badge">slm</div>
      </div>
    </div>
  );
}
