import { useEffect, useState } from "react";
import { api } from "../api";

type Diag = {
  health: any;
  requestCounts: Record<string, number>;
  recentSearches: any[];
  collections: Record<string, number>;
};

export default function Diagnostics() {
  const [d, setD] = useState<Diag | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const load = () => api.diagnostics().then((x) => setD(x as Diag)).catch((e) => setErr(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  if (err) return <p className="banner banner-error">{err}</p>;
  if (!d) return <p className="muted">Loading diagnostics…</p>;
  const providers = d.health.providers as Record<string, any>;
  return (
    <div className="diag">
      <p>
        <a href="#/">← Back to ClipCart</a>
      </p>
      <h2>Diagnostics</h2>
      <p className="muted">No secrets are shown. “Live” means a real call succeeded since the server started.</p>
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Mode</th>
            <th>Calls</th>
            <th>Failures</th>
            <th>Last success</th>
            <th>Last error</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(providers).map(([k, p]) => (
            <tr key={k}>
              <td>
                {k} {p.model ? <small className="muted">{p.model}</small> : null}
              </td>
              <td>
                <span className={`mode mode-${p.mode}`}>{p.mode}</span>
              </td>
              <td>{p.calls}</td>
              <td>{p.failures}</td>
              <td>{p.lastSuccessAt ? new Date(p.lastSuccessAt).toLocaleTimeString() : "—"}</td>
              <td>{p.lastError ? `${p.lastError.code ?? ""} ${p.lastError.traceId ? `trace ${p.lastError.traceId}` : ""} ${p.lastError.note ?? ""}` : "—"}</td>
            </tr>
          ))}
          <tr>
            <td>database</td>
            <td>
              <span className="mode">{d.health.database.mode}</span>
            </td>
            <td colSpan={4}>{d.health.database.note ?? (d.health.database.ok ? "ping ok" : "ping failed")}</td>
          </tr>
        </tbody>
      </table>
      <h3>Feature flags</h3>
      <p>{Object.entries(d.health.features).map(([k, v]) => `${k}: ${v ? "on" : "off"}`).join(" · ")}</p>
      <h3>Request counts</h3>
      <p>{Object.entries(d.requestCounts).map(([k, v]) => `${k}: ${v}`).join(" · ") || "none yet"}</p>
      <h3>Recent searches</h3>
      <table>
        <thead>
          <tr>
            <th>Search</th>
            <th>Status</th>
            <th>Workers</th>
            <th>Catalog</th>
            <th>Calls</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>
          {d.recentSearches.map((j) => (
            <tr key={j.id}>
              <td>
                <code>{j.id}</code>
              </td>
              <td>{j.status}</td>
              <td>{j.workerModes ? Object.entries(j.workerModes).map(([k, v]) => `${k}: ${v}`).join(", ") : j.workerMode}</td>
              <td>{j.catalogMode}</td>
              <td>
                {j.budget?.usedToolCalls}/{j.budget?.maxToolCalls} ({j.budget?.usedDetailCalls} detail, {j.budget?.reasoningCalls} reasoning)
              </td>
              <td>{j.summary ?? j.error?.code ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
