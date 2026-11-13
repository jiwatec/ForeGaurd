import React, { useCallback, useEffect, useRef, useState } from "react";

const PAGE_SIZE = 20;
const FILTERS = ["ALL", "PENDING", "APPROVED", "REJECTED", "EXPIRED", "BLOCK", "ALLOW"];

function date(value) {
  return new Date(value * 1000).toLocaleString();
}

function RequestCard({ record, onDecide, busy }) {
  const reviewable = record.status === "PENDING";
  return (
    <article className="request-card">
      <div className="card-top">
        <span className={`badge badge-${record.status.toLowerCase()}`}>{record.status}</span>
        <span className="request-date">{date(record.created)}</span>
      </div>
      <pre className="command">{record.command}</pre>
      <div className="record-details">
        <p><span>Working directory</span><strong>{record.cwd}</strong></p>
        <p><span>Source</span><strong>{record.source}</strong></p>
        <p><span>Assessment</span><strong>{record.assessment.decision} · {record.assessment.category} · {record.assessment.risk_score}/100</strong></p>
        <p><span>Reason</span><strong>{record.assessment.reasons.join("; ")}</strong></p>
        <p><span>Expires</span><strong>{date(record.expires)}</strong></p>
        <p><span>Request ID</span><strong className="request-id">{record.id}</strong></p>
      </div>
      {reviewable && (
        <div className="card-actions">
          <button type="button" className="approve" disabled={busy} onClick={() => onDecide(record, "APPROVE")}>Approve request</button>
          <button type="button" className="reject" disabled={busy} onClick={() => onDecide(record, "REJECT")}>Reject</button>
        </div>
      )}
    </article>
  );
}

export default function Dashboard() {
  const [entry, setEntry] = useState("");
  const [token, setToken] = useState("");
  const [records, setRecords] = useState([]);
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("ALL");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Enter your admin token to load requests.");
  const [error, setError] = useState(false);
  const [hasNext, setHasNext] = useState(false);
  const sequence = useRef(0);
  const working = useRef(false);

  const load = useCallback(async (secret, currentPage, quiet = false) => {
    if (!secret || working.current || document.hidden) return false;
    const requestSequence = ++sequence.current;
    working.current = true;
    if (!quiet) { setBusy(true); setMessage("Loading requests…"); setError(false); }
    try {
      const response = await fetch(`/api/requests?limit=${PAGE_SIZE}&offset=${currentPage * PAGE_SIZE}`, {
        headers: { Authorization: `Bearer ${secret}` }, cache: "no-store",
      });
      if (!response.ok) throw new Error(response.status === 401 ? "Access denied. Check your token." : "Could not load requests. Try again.");
      const data = await response.json();
      if (requestSequence !== sequence.current) return false;
      setRecords(data.requests);
      setHasNext(data.requests.length === PAGE_SIZE);
      setMessage(data.requests.length ? `Showing ${data.requests.length} requests on this page.` : "No requests on this page.");
      setError(false);
      return true;
    } catch (cause) {
      setRecords([]);
      setHasNext(false);
      setMessage(cause.message);
      setError(true);
      return false;
    } finally {
      working.current = false;
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!token) return undefined;
    const timer = setInterval(() => { load(token, page, true); }, 15000);
    return () => clearInterval(timer);
  }, [token, page, load]);

  function connect(event) {
    event.preventDefault();
    if (!entry.trim()) { setMessage("Enter a token first."); setError(true); return; }
    const secret = entry;
    setEntry("");
    setToken(secret);
    setPage(0);
    setRecords([]);
    setFilter("ALL");
    load(secret, 0);
  }

  function changePage(next) {
    setPage(next);
    setRecords([]);
    load(token, next);
  }

  async function decide(record, decision) {
    if (working.current || !token) return;
    if (!window.confirm(`${decision === "APPROVE" ? "Approve" : "Reject"} this exact request? No command will be executed.`)) return;
    working.current = true;
    setBusy(true);
    setMessage("Saving decision…");
    setError(false);
    try {
      const response = await fetch(`/api/requests/${encodeURIComponent(record.id)}/decide`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ command: record.command, cwd: record.cwd, source: record.source, decision }),
        cache: "no-store",
      });
      if (response.status === 409) {
        working.current = false;
        if (await load(token, page)) { setMessage("Decision not applied: request changed or expired."); setError(true); }
        return;
      }
      if (!response.ok) throw new Error(response.status === 401 ? "Access denied. Check your token." : "Decision failed. Try again or refresh.");
      working.current = false;
      await load(token, page);
    } catch (cause) {
      setMessage(cause.message);
      setError(true);
      if (cause.message.startsWith("Access denied")) setRecords([]);
    } finally {
      working.current = false;
      setBusy(false);
    }
  }

  const visible = filter === "ALL" ? records : records.filter(record => record.status === filter);
  const pending = records.filter(record => record.status === "PENDING").length;
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand"><span className="brand-icon">F</span><span>Fore<span className="brand-accent">Guard</span><small>LOCAL REVIEW CONSOLE</small></span></div>
        <div className="sidebar-section">WORKSPACE</div>
        <div className="nav-active"><span className="nav-dot" />Request review</div>
        <div className="sidebar-note"><strong>Assessment only</strong><p>Approving a request records a decision. It never runs a command.</p></div>
        <div className="sidebar-footer"><span className="online-dot" /> Local service · 127.0.0.1</div>
      </aside>
      <main className="main">
        <header className="topbar"><span>WORKSPACE / REQUEST REVIEW</span><span className="local-tag">● LOCAL MODE</span></header>
        <div className="content">
          <div className="page-heading"><div><span className="eyebrow">COMMAND SAFETY</span><h1>Review requests</h1><p>Inspect assessments and record human decisions from one place.</p></div><span className="phase-tag">PHASE 3 · REVIEW & AUDIT</span></div>
          <form className="access-panel" onSubmit={connect}>
            <div><h2>Local access</h2><p>Enter the admin token configured on this service. It stays in this page’s memory only.</p></div>
            <div className="access-controls"><label className="sr-only" htmlFor="token">Admin token</label><input id="token" type="password" autoComplete="off" spellCheck="false" placeholder="Admin token" value={entry} onChange={event => setEntry(event.target.value)} /><button type="submit" disabled={busy}>{token ? "Reconnect" : "Connect"}</button></div>
          </form>
          <div className="stats"><div className="stat"><span>REQUESTS ON PAGE</span><strong>{records.length}</strong><small>Latest assessments</small></div><div className="stat"><span>AWAITING REVIEW</span><strong className="amber">{pending}</strong><small>Action required</small></div><div className="stat"><span>CONNECTION</span><strong className="connection">{token ? "Active" : "Offline"}</strong><small>Local session only</small></div></div>
          <section className="review-section" aria-labelledby="review-heading">
            <div className="section-heading"><div><h2 id="review-heading">Request history</h2><p>Showing the newest requests first · auto-refreshes every 15 seconds</p></div><button type="button" className="refresh" disabled={!token || busy} onClick={() => load(token, page)}>↻ Refresh</button></div>
            <div className="filters" role="group" aria-label="Filter requests on this page">{FILTERS.map(option => <button key={option} type="button" className={filter === option ? "filter active" : "filter"} aria-pressed={filter === option} onClick={() => setFilter(option)}>{option === "ALL" ? "All requests" : option}</button>)}</div>
            <p className={error ? "feedback error" : "feedback"} role="status" aria-live="polite">{message}</p>
            {busy && <div className="loading" aria-label="Loading" />}
            <div className="cards">{visible.map(record => <RequestCard key={record.id} record={record} onDecide={decide} busy={busy} />)}</div>
            {!busy && token && !error && visible.length === 0 && records.length > 0 && <p className="empty">No {filter.toLowerCase()} requests on this page.</p>}
            <nav className="pagination" aria-label="History pages"><button type="button" disabled={!token || busy || page === 0} onClick={() => changePage(page - 1)}>← Previous</button><span>Page {page + 1}</span><button type="button" disabled={!token || busy || !hasNext} onClick={() => changePage(page + 1)}>Next →</button></nav>
          </section>
          <footer>FOREGUARD · Local-first command review · Approval is not execution permission.</footer>
        </div>
      </main>
    </div>
  );
}
