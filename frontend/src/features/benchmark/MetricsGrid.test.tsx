import { render, screen } from "@testing-library/react";
import type { OptimizationResult } from "../../api/contracts";
import { MetricsGrid } from "./MetricsGrid";

const result: OptimizationResult = {
  request_id: "req-1",
  dataset_hash: "sha256:abc",
  config_hash: "sha256:cfg",
  selected_date: "2026-08-26",
  benchmark_label: "Perfect-hindsight benchmark—not a live trading forecast.",
  battery: { capacity_mwh: "200" },
  solver: {
    pulp_version: "3.3.2",
    cbc_version: "2.10.3",
    executable_path: "cbc",
    executable_sha256: null,
    options: ["threads=1"],
  },
  metrics: {
    gross_simulated_revenue_aud: "24973.34117499342833333333332",
    imported_mwh: "798.1481445833333333333333306",
    exported_mwh: "718.3333310833333333333333308",
    throughput_mwh: "1516.481475666666666666666661",
    equivalent_full_cycles: "3.791203689166666666666666652",
    ending_soc_mwh: "99.99999898982796966843438208",
    idle_preference_objective: "186.0",
    solve_wall_time_s: 1,
    verification_passed: true,
  },
  decisions: [],
  verification: { passed: true, failures: [] },
  provenance: {},
  stage_evidence: [],
};

it("rounds headline metrics to two decimals and leaves solver status unrounded", () => {
  render(<MetricsGrid result={result} />);
  expect(screen.getByTestId("metric-revenue")).toHaveTextContent("24973.34 AUD");
  expect(screen.getByText("100.00 MWh")).toBeInTheDocument();
  expect(screen.getByText("798.15 MWh")).toBeInTheDocument();
  expect(screen.getByText("718.33 MWh")).toBeInTheDocument();
  expect(screen.getByText("1516.48 MWh / 3.79")).toBeInTheDocument();
  expect(screen.getByText("CBC Optimal · verified")).toBeInTheDocument();
  expect(screen.queryByText(/24973\.34117499342833333333332/)).not.toBeInTheDocument();
});
