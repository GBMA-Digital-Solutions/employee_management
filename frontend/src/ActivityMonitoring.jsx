import { useEffect, useState } from "react";
import { classifyActivityDomain, fetchActivityMonitoring } from "./api";
import { today } from "./managerConfig";

const categories = ["work", "social", "entertainment", "other"];
const title = (value) => value === "work" ? "Work-related" : value.replace(/^./, (letter) => letter.toUpperCase());
const duration = (seconds) => {
  const minutes = Math.round(Number(seconds || 0) / 60);
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};

export default function ActivityMonitoring({ token, onAuthError }) {
  const [filters, setFilters] = useState({ employee: "", period: "daily", date: today() });
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => fetchActivityMonitoring(token, filters).then((result) => {
    setReport(result); setError("");
  }).catch((err) => { setError(err.message); onAuthError(err); });

  useEffect(() => { load(); }, [token, filters.employee, filters.period, filters.date]); // eslint-disable-line react-hooks/exhaustive-deps

  async function classify(domain, category) {
    setBusy(true); setError("");
    try {
      await classifyActivityDomain(token, domain, category);
      await load();
      setNotice(`${domain} classified as ${title(category)}.`);
    } catch (err) { setError(err.message); onAuthError(err); }
    finally { setBusy(false); }
  }

  return <>
    <div className="section-heading"><div><p className="eyebrow dark-eyebrow">WORKPLACE ACTIVITY</p><h2>Activity Monitoring</h2><p>Review website and application usage during working hours.</p></div></div>
    {error && <p className="message error" role="alert">{error}</p>}
    {notice && <p className="message success" role="status">{notice}</p>}
    <section className="panel activity-filters">
      <div><label htmlFor="activity-employee">Employee</label><select id="activity-employee" value={filters.employee} onChange={(event) => setFilters((current) => ({ ...current, employee: event.target.value }))}><option value="">All employees</option>{report?.employees?.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></div>
      <div><label htmlFor="activity-period">Report</label><select id="activity-period" value={filters.period} onChange={(event) => setFilters((current) => ({ ...current, period: event.target.value }))}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></div>
      <div><label htmlFor="activity-date">Report date</label><input id="activity-date" type="date" value={filters.date} onChange={(event) => setFilters((current) => ({ ...current, date: event.target.value }))} /></div>
    </section>
    {!report ? <p className="empty-state">Loading activity…</p> : report.total_seconds === 0 ? <section className="panel records-panel"><p className="empty-state">No data yet.</p></section> : <>
      <div className="summary-grid activity-summary">
        <div className="summary-card"><span>Total monitored time</span><strong>{duration(report.total_seconds)}</strong><small>{report.start_date} to {report.end_date}</small></div>
        {report.categories.filter((row) => row.duration_seconds > 0).map((row) => <div className="summary-card" key={row.category}><span>{title(row.category)}</span><strong>{duration(row.duration_seconds)}</strong></div>)}
      </div>
      <section className="panel records-panel"><div className="records-heading"><div><h3>Websites and applications</h3><p>Time is summed for the selected reporting period.</p></div></div><div className="table-wrap"><table><thead><tr><th>Resource</th><th>Type</th><th>Category</th><th>Time spent</th></tr></thead><tbody>{report.resources.map((row) => <tr key={`${row.kind}-${row.resource}`}><td><strong>{row.resource}</strong>{row.domain && <small>{row.domain}</small>}</td><td>{title(row.kind)}</td><td>{row.kind === "website" ? <select disabled={busy} value={row.category} onChange={(event) => classify(row.domain, event.target.value)}>{categories.map((category) => <option key={category} value={category}>{title(category)}</option>)}</select> : "Other"}</td><td>{duration(row.duration_seconds)}</td></tr>)}</tbody></table></div></section>
      <section className="panel records-panel"><div className="records-heading"><div><h3>Activity timeline</h3><p>Most recent collected intervals.</p></div></div><div className="activity-timeline">{report.timeline.map((row) => <div key={row.id}><time>{new Date(row.started_at).toLocaleString()} – {new Date(row.ended_at).toLocaleTimeString()}</time><strong>{row.resource}</strong><span>{row.employee_name} · {title(row.category)} · {duration(row.duration_seconds)}</span></div>)}</div></section>
    </>}
  </>;
}
