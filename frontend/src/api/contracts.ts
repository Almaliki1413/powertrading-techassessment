export type DaySummary = {
  date: string;
  status: string;
  selectable: boolean;
  interval_count: number | null;
  rrp_min: string | null;
  rrp_max: string | null;
  blocking_code: string | null;
  blocking_message: string | null;
  source_hash?: string | null;
  inspection_status?: string;
};

export type ProblemDetails = {
  code: string;
  message: string;
  blocking: boolean;
  request_id: string;
  details?: Record<string, unknown>;
};

export type Decision = {
  interval_end: string;
  rrp_aud_per_mwh: string;
  action: "charge" | "discharge" | "idle";
  signed_power_mw: string;
  imported_mwh: string;
  exported_mwh: string;
  soc_before_mwh: string;
  soc_after_mwh: string;
  interval_cash_flow_aud: string;
  cumulative_cash_flow_aud: string;
  reason_code: string;
  reason_text: string;
  binding_constraints: string[];
  price_percentile: string;
};

export type OptimizationResult = {
  request_id: string;
  dataset_hash: string;
  config_hash: string;
  selected_date: string;
  benchmark_label: string;
  battery: Record<string, string>;
  solver: {
    pulp_version: string;
    cbc_version: string;
    executable_path: string;
    executable_sha256: string | null;
    options: string[];
  };
  metrics: {
    gross_simulated_revenue_aud: string;
    imported_mwh: string;
    exported_mwh: string;
    throughput_mwh: string;
    equivalent_full_cycles: string;
    ending_soc_mwh: string;
    idle_preference_objective: string;
    solve_wall_time_s: number;
    verification_passed: boolean;
  };
  decisions: Decision[];
  verification: { passed: boolean; failures: string[] };
  provenance: Record<string, unknown>;
  stage_evidence: Array<{
    stage: number;
    objective_name: string;
    status: string;
    objective_value: string | null;
    wall_time_s: number;
  }>;
};

export type AppState =
  | "initial"
  | "resolving_dataset"
  | "ready"
  | "solving"
  | "success"
  | "blocking_failure";
