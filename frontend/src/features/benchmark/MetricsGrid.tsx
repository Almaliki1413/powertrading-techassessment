import type { OptimizationResult } from "../../api/contracts";

function Metric({
  label,
  value,
  testId,
  featured = false,
}: {
  label: string;
  value: string;
  testId?: string;
  featured?: boolean;
}) {
  return (
    <div className={featured ? "metric featured" : "metric"}>
      <span>{label}</span>
      <strong data-testid={testId}>{value}</strong>
    </div>
  );
}

export function MetricsGrid({ result }: { result: OptimizationResult | null }) {
  if (!result) {
    return (
      <section className="metrics" aria-label="Headline metrics">
        <Metric label="Gross simulated revenue" value="—" featured />
        <Metric label="Ending SoC" value="—" />
        <Metric label="Imported energy" value="—" />
        <Metric label="Exported energy" value="—" />
        <Metric label="Throughput / cycles" value="—" />
        <Metric label="Solver / verification" value="—" />
      </section>
    );
  }
  const m = result.metrics;
  return (
    <section className="metrics" aria-label="Headline metrics">
      <Metric
        label="Gross simulated revenue"
        value={`${m.gross_simulated_revenue_aud} AUD`}
        testId="metric-revenue"
        featured
      />
      <Metric label="Selected day" value={result.selected_date} />
      <Metric label="Ending SoC" value={`${m.ending_soc_mwh} MWh`} />
      <Metric label="Imported energy" value={`${m.imported_mwh} MWh`} />
      <Metric label="Exported energy" value={`${m.exported_mwh} MWh`} />
      <Metric
        label="Throughput / equivalent full cycles"
        value={`${m.throughput_mwh} MWh / ${m.equivalent_full_cycles}`}
      />
      <Metric
        label="Solver / verification"
        value={`${result.solver.cbc_version ? "CBC Optimal" : "CBC"} · ${
          m.verification_passed ? "verified" : "failed"
        }`}
      />
    </section>
  );
}
