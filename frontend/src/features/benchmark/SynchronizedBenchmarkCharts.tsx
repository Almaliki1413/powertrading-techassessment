import Plot from "react-plotly.js";
import type { Decision } from "../../api/contracts";

const ink = "#3c362c";
const rule = "#c4b79d";
const charge = "#0c5853";
const discharge = "#b44512";
const paperLine = "#1b1712";
const soc = "#2c5a32";
const bound = "#8a1c18";
const target = "#8d5310";

const layoutBase = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: ink, family: "IBM Plex Sans, Segoe UI, sans-serif", size: 11 },
  margin: { l: 52, r: 16, t: 34, b: 44 },
  hovermode: "x unified" as const,
  xaxis: {
    title: "Interval end (NEM market time)",
    gridcolor: rule,
    zerolinecolor: rule,
    linecolor: rule,
  },
  yaxis: {
    gridcolor: rule,
    zerolinecolor: rule,
    linecolor: rule,
  },
};

export function SynchronizedBenchmarkCharts({ decisions }: { decisions: Decision[] }) {
  const x = decisions.map((d) => d.interval_end);
  const rrp = decisions.map((d) => Number(d.rrp_aud_per_mwh));
  const power = decisions.map((d) => Number(d.signed_power_mw));
  const socAfter = decisions.map((d) => Number(d.soc_after_mwh));
  const revenue = decisions.map((d) => Number(d.cumulative_cash_flow_aud));
  const chargeX = decisions.filter((d) => d.action === "charge").map((d) => d.interval_end);
  const chargeY = decisions.filter((d) => d.action === "charge").map((d) => Number(d.rrp_aud_per_mwh));
  const dischargeX = decisions.filter((d) => d.action === "discharge").map((d) => d.interval_end);
  const dischargeY = decisions.filter((d) => d.action === "discharge").map((d) => Number(d.rrp_aud_per_mwh));

  return (
    <section className="charts" aria-label="Synchronized benchmark charts">
      <div className="chart-summary">
        <p className="muted">
          Four charts share the same 288 interval-ending timestamps. Export power is positive, and SoC
          bounds are 0–200 MWh with a 100 MWh terminal target.
        </p>
        <p className="legend">
          <span>
            <i className="swatch charge" />
            Charge
          </span>
          <span>
            <i className="swatch discharge" />
            Discharge
          </span>
        </p>
      </div>
      <div className="chart-grid">
        <div className="chart-cell">
          <Plot
            aria-label="NSW1 RRP with charge and discharge markers"
            data={[
              {
                x,
                y: rrp,
                type: "scatter",
                mode: "lines",
                name: "NSW1 RRP AUD/MWh",
                line: { color: paperLine, width: 1.4 },
              },
              {
                x: chargeX,
                y: chargeY,
                type: "scatter",
                mode: "markers",
                name: "Charge",
                marker: { color: charge, size: 6, symbol: "square" },
              },
              {
                x: dischargeX,
                y: dischargeY,
                type: "scatter",
                mode: "markers",
                name: "Discharge",
                marker: { color: discharge, size: 6, symbol: "diamond" },
              },
            ]}
            layout={{
              ...layoutBase,
              title: { text: "NSW1 RRP (AUD/MWh)", font: { family: "Newsreader, serif", size: 16 } },
              yaxis: { ...layoutBase.yaxis, title: "AUD/MWh" },
            }}
            useResizeHandler
            style={{ width: "100%", height: 260 }}
            config={{ displayModeBar: false }}
          />
        </div>
        <div className="chart-cell">
          <Plot
            aria-label="Signed battery power"
            data={[
              {
                x,
                y: power,
                type: "scatter",
                mode: "lines",
                name: "Signed MW",
                line: { color: charge, width: 1.4 },
                fill: "tozeroy",
                fillcolor: "rgba(12, 88, 83, 0.12)",
              },
            ]}
            layout={{
              ...layoutBase,
              title: {
                text: "Signed battery power — export +, import −",
                font: { family: "Newsreader, serif", size: 16 },
              },
              yaxis: { ...layoutBase.yaxis, title: "MW" },
            }}
            useResizeHandler
            style={{ width: "100%", height: 260 }}
            config={{ displayModeBar: false }}
          />
        </div>
        <div className="chart-cell">
          <Plot
            aria-label="State of charge"
            data={[
              {
                x,
                y: socAfter,
                type: "scatter",
                mode: "lines",
                name: "SoC after",
                line: { color: soc, width: 1.5 },
              },
              {
                x: [x[0], x[x.length - 1]],
                y: [200, 200],
                type: "scatter",
                mode: "lines",
                name: "SoC max",
                line: { color: bound, dash: "dot", width: 1 },
              },
              {
                x: [x[0], x[x.length - 1]],
                y: [0, 0],
                type: "scatter",
                mode: "lines",
                name: "SoC min",
                line: { color: bound, dash: "dot", width: 1 },
              },
              {
                x: [x[0], x[x.length - 1]],
                y: [100, 100],
                type: "scatter",
                mode: "lines",
                name: "Terminal target",
                line: { color: target, dash: "dash", width: 1 },
              },
            ]}
            layout={{
              ...layoutBase,
              title: { text: "State of charge (MWh)", font: { family: "Newsreader, serif", size: 16 } },
              yaxis: { ...layoutBase.yaxis, title: "MWh", range: [-5, 210] },
            }}
            useResizeHandler
            style={{ width: "100%", height: 260 }}
            config={{ displayModeBar: false }}
          />
        </div>
        <div className="chart-cell">
          <Plot
            aria-label="Cumulative revenue"
            data={[
              {
                x,
                y: revenue,
                type: "scatter",
                mode: "lines",
                name: "Cumulative AUD",
                line: { color: discharge, width: 1.6 },
              },
            ]}
            layout={{
              ...layoutBase,
              title: {
                text: "Cumulative gross simulated cash flow",
                font: { family: "Newsreader, serif", size: 16 },
              },
              yaxis: { ...layoutBase.yaxis, title: "AUD" },
            }}
            useResizeHandler
            style={{ width: "100%", height: 260 }}
            config={{ displayModeBar: false }}
          />
        </div>
      </div>
    </section>
  );
}
