import { useEffect, useMemo, useRef, useState } from "react";
import { fetchConfig, resolveDataset, runOptimization } from "../api/client";
import type { AppState, DaySummary, OptimizationResult, ProblemDetails } from "../api/contracts";
import { BenchmarkBanner } from "../components/BenchmarkBanner";
import { IntervalAuditTable } from "../features/audit-table/IntervalAuditTable";
import { describeBlockingProblem } from "../features/benchmark/blockingReason";
import { MetricsGrid } from "../features/benchmark/MetricsGrid";
import { SynchronizedBenchmarkCharts } from "../features/benchmark/SynchronizedBenchmarkCharts";
import { DatasetToolbar } from "../features/dataset/DatasetToolbar";

const LABEL = "Perfect-hindsight benchmark—not a live trading forecast.";

export function App() {
  const [state, setState] = useState<AppState>("initial");
  const [label, setLabel] = useState(LABEL);
  const [range, setRange] = useState({ start: "2026-08-26", end: "2026-09-01", defaultDate: "2026-08-26" });
  const [days, setDays] = useState<DaySummary[]>([]);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState("2026-08-26");
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [problem, setProblem] = useState<ProblemDetails | null>(null);
  const [statusText, setStatusText] = useState("Loading pinned dataset");
  const [battery, setBattery] = useState<Record<string, string>>({});
  const [inFlight, setInFlight] = useState(false);
  const selectedDateRef = useRef(selectedDate);
  selectedDateRef.current = selectedDate;

  const selected = days.find((day) => day.date === selectedDate);
  const canSolve = Boolean(datasetId && selected?.selectable && !inFlight);
  const blockingView = problem ? describeBlockingProblem(problem) : null;

  async function loadDataset() {
    setState("resolving_dataset");
    setResult(null);
    setProblem(null);
    setStatusText("Resolving pinned dataset");
    try {
      const config = await fetchConfig();
      setLabel(config.benchmark_label);
      setRange({
        start: config.pinned_range.start_date,
        end: config.pinned_range.end_date,
        defaultDate: config.pinned_range.default_date,
      });
      setBattery(config.battery);
      const resolved = await resolveDataset(
        config.pinned_range.start_date,
        config.pinned_range.end_date,
        "pinned",
      );
      setDatasetId(resolved.dataset_id);
      setDays(resolved.days);
      const preferred =
        resolved.days.find((day) => day.date === config.pinned_range.default_date && day.selectable) ??
        resolved.days.find((day) => day.selectable);
      setSelectedDate(preferred?.date ?? config.pinned_range.default_date);
      setState("ready");
      setStatusText("Dataset ready. Select a validated day and run the benchmark.");
    } catch (error) {
      setProblem(error as ProblemDetails);
      setState("blocking_failure");
      setStatusText("Pinned dataset failed a blocking gate.");
    }
  }

  useEffect(() => {
    void loadDataset();
  }, []);

  async function onSolve() {
    if (!datasetId || !selected?.selectable || inFlight) return;
    const dateAtStart = selectedDate;
    setInFlight(true);
    setState("solving");
    setProblem(null);
    setStatusText("Running three-stage CBC solve and independent verification");
    try {
      const next = await runOptimization(datasetId, dateAtStart);
      if (selectedDateRef.current !== dateAtStart) {
        setResult(null);
        setProblem(null);
        setState("ready");
        setStatusText("Previous solve finished. Run again for the selected day.");
        return;
      }
      setResult(next);
      setState("success");
      setStatusText(`Verified benchmark for ${next.selected_date}`);
    } catch (error) {
      if (selectedDateRef.current !== dateAtStart) {
        setResult(null);
        setProblem(null);
        setState("ready");
        setStatusText("Previous solve finished. Run again for the selected day.");
        return;
      }
      setResult(null);
      setProblem(error as ProblemDetails);
      setState("blocking_failure");
      setStatusText("Optimization blocked.");
    } finally {
      setInFlight(false);
    }
  }

  function onDateChange(value: string) {
    setSelectedDate(value);
    setResult(null);
    setProblem(null);
    if (inFlight) {
      setStatusText("Selected day changed. Waiting for the in-flight solve to finish.");
      return;
    }
    setState("ready");
    setStatusText("Selected day changed. Previous results cleared.");
  }

  const assumptions = useMemo(
    () => [
      ["Capacity", `${battery.capacity_mwh ?? "200"} MWh`],
      ["Charge / discharge", `${battery.charge_limit_mw ?? "100"} / ${battery.discharge_limit_mw ?? "100"} MW`],
      ["Initial / terminal SoC", `${battery.initial_soc_mwh ?? "100"} / ${battery.terminal_soc_mwh ?? "100"} MWh`],
      ["Round-trip efficiency", "90% split as ηc = ηd = √0.90"],
      ["Interval", "5 minutes = 1/12 hour"],
      ["Revenue scope", "Gross energy-market cash flow only"],
    ],
    [battery],
  );

  return (
    <div className="desk">
      <main className="sheet">
        <header className="masthead">
          <div className="masthead-top">
            <span>AEMO DispatchIS · NSW1 · pinned archive</span>
            <span>
              {range.start} → {range.end}
            </span>
          </div>
          <div className="masthead-title-row">
            <h1>BESS hindsight blotter</h1>
            <BenchmarkBanner label={label} />
          </div>
        </header>
        <p className="status-rail" role="status" aria-live="polite">
          <span>{statusText}</span>
          <span title={datasetId ?? undefined}>
            {datasetId ? `${datasetId.slice(0, 19)}…` : "dataset unresolved"}
          </span>
        </p>
        <DatasetToolbar
          sourceMode="pinned"
          days={days}
          selectedDate={selectedDate}
          onDateChange={onDateChange}
          onSolve={() => void onSolve()}
          solving={inFlight}
          canSolve={canSolve}
        />
        {problem && blockingView ? (
          <section className="panel problem" role="alert">
            <h2>Blocking problem</h2>
            <p>
              <strong>{problem.code}</strong>: {problem.message}
            </p>
            <p>{blockingView.reason}</p>
            <ol className="gate-list" aria-label="Solve gates">
              {blockingView.gates.map((gate) => (
                <li key={gate.id} className={`gate-${gate.state}`}>
                  <span className="gate-state">
                    {gate.state === "passed" ? "Passed" : gate.state === "failed" ? "Failed" : "Not reached"}
                  </span>
                  <span>{gate.label}</span>
                </li>
              ))}
            </ol>
            {typeof problem.details?.status === "string" ||
            typeof problem.details?.wall_time_s === "number" ||
            problem.details?.killed === true ? (
              <p className="muted">
                {typeof problem.details.status === "string" ? `CBC status: ${problem.details.status}. ` : null}
                {problem.details.killed === true ? "Terminated by hard deadline. " : null}
                {typeof problem.details.wall_time_s === "number"
                  ? `Stage wall time ${Number(problem.details.wall_time_s).toFixed(1)}s.`
                  : null}
              </p>
            ) : null}
            <p className="muted">Request {problem.request_id}. Previous optimization results are not shown as current.</p>
          </section>
        ) : null}
        <MetricsGrid result={state === "success" ? result : null} />
        {state === "success" && result ? (
          <>
            <SynchronizedBenchmarkCharts decisions={result.decisions} />
            <IntervalAuditTable decisions={result.decisions} />
          </>
        ) : problem ? null : (
          <section className="panel awaiting">
            <h2>{days.length > 0 && days.every((d) => !d.selectable) ? "No validated day" : "Awaiting verified schedule"}</h2>
            <p className="muted">
              The UI never fabricates demo output. Charts and the audit table appear only after CBC returns an
              Optimal status and the independent verifier passes.
            </p>
          </section>
        )}
        <footer className="ledger">
          <details>
            <summary>Assumptions</summary>
            <div className="assumptions">
              {assumptions.map(([k, v]) => (
                <div key={k}>
                  <div className="muted">{k}</div>
                  <div>{v}</div>
                </div>
              ))}
            </div>
          </details>
          <details>
            <summary>Provenance</summary>
            <p className="muted hash">
              Pinned range {range.start} → {range.end}. Dataset {datasetId ?? "unresolved"}.
              {result
                ? ` Result dataset hash ${result.dataset_hash}; config hash ${result.config_hash}; PuLP ${result.solver.pulp_version}.`
                : " Run a verified day to attach solver hashes."}
            </p>
          </details>
          <details>
            <summary>Methodology and limitations</summary>
            <ul>
              <li>This is a perfect-hindsight benchmark, not a live trading forecast.</li>
              <li>Price-taker energy-only cash flow; no FCAS, fees, degradation, or market impact.</li>
              <li>Reason codes describe binding constraints and the global MILP; they are not local threshold rules.</li>
              <li>Days remain unselectable until archive safety, schema, completeness, and firm-price gates pass.</li>
            </ul>
          </details>
        </footer>
      </main>
    </div>
  );
}
