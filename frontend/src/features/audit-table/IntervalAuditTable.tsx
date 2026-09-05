import type { Decision } from "../../api/contracts";

export function IntervalAuditTable({ decisions }: { decisions: Decision[] }) {
  return (
    <section className="table-wrap" aria-label="Interval audit table">
      <h2>Interval audit table</h2>
      <p className="muted">
        Chronological source-precision values from the verified API response. Formatting here is display-only.
      </p>
      <table>
        <thead>
          <tr>
            <th>Interval end</th>
            <th className="num">RRP</th>
            <th>Action</th>
            <th className="num">Signed MW</th>
            <th className="num">Imported MWh</th>
            <th className="num">Exported MWh</th>
            <th className="num">SoC before</th>
            <th className="num">SoC after</th>
            <th className="num">Interval AUD</th>
            <th className="num">Cumulative AUD</th>
            <th>Reason</th>
            <th>Why not idle / opposite</th>
            <th>Bindings</th>
          </tr>
        </thead>
        <tbody>
          {decisions.map((d) => (
            <tr key={d.interval_end}>
              <td>{d.interval_end}</td>
              <td className="num">{d.rrp_aud_per_mwh}</td>
              <td>
                <span className={`action-pill ${d.action}`}>{d.action}</span>
              </td>
              <td className="num">{d.signed_power_mw}</td>
              <td className="num">{d.imported_mwh}</td>
              <td className="num">{d.exported_mwh}</td>
              <td className="num">{d.soc_before_mwh}</td>
              <td className="num">{d.soc_after_mwh}</td>
              <td className="num">{d.interval_cash_flow_aud}</td>
              <td className="num">{d.cumulative_cash_flow_aud}</td>
              <td>{d.reason_code}</td>
              <td className="contrast">{d.reason_text}</td>
              <td>{d.binding_constraints.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
