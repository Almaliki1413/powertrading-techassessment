import type { ProblemDetails } from "../../api/contracts";

export type GateState = "passed" | "failed" | "not_reached";

export type SolveGate = {
  id: string;
  label: string;
  state: GateState;
};

const GATES: Array<{ id: string; label: string }> = [
  { id: "dataset", label: "Dataset quality — 288 NSW1 firm prices" },
  { id: "cbc_stage_1", label: "CBC stage 1 — maximize revenue" },
  { id: "cbc_stage_2", label: "CBC stage 2 — minimize throughput at that revenue" },
  { id: "cbc_stage_3", label: "CBC stage 3 — prefer idle among remaining ties" },
  { id: "verifier", label: "Independent verifier — no PuLP" },
];

const STATUS_REASON: Record<string, string> = {
  "Not Solved":
    "CBC stopped before proving optimality. Typical causes are a time limit, an interrupt, or a search that never closed the gap.",
  Infeasible:
    "CBC found no schedule that keeps stage-1 revenue within 1e-6 AUD while obeying battery physics. This can be a knife-edge numerical bound, not missing prices.",
  Unbounded: "CBC reported an unbounded model. That is a formulation defect, not a market result.",
  Undefined: "CBC returned no usable termination status (no complete solution file).",
};

function failedGateId(problem: ProblemDetails): string | null {
  const details = problem.details ?? {};
  if (typeof details.failed_gate === "string") return details.failed_gate;
  if (problem.code === "POST_SOLVE_VERIFICATION_FAILED") return "verifier";
  if (problem.code === "SOLVER_BUSY") return "cbc_stage_1";
  if (typeof details.stage === "number") return `cbc_stage_${details.stage}`;
  if (problem.code === "SOLVER_FAILED") return "cbc_stage_1";
  return null;
}

export function describeBlockingProblem(problem: ProblemDetails): {
  reason: string;
  gates: SolveGate[];
} {
  const details = problem.details ?? {};
  const failed = failedGateId(problem);
  const gates = GATES.map((gate, index) => {
    if (!failed) return { ...gate, state: "not_reached" as const };
    const failIndex = GATES.findIndex((item) => item.id === failed);
    if (failIndex < 0) return { ...gate, state: "not_reached" as const };
    if (index < failIndex) return { ...gate, state: "passed" as const };
    if (index === failIndex) return { ...gate, state: "failed" as const };
    return { ...gate, state: "not_reached" as const };
  });

  if (typeof details.reason === "string" && details.reason.trim()) {
    return { reason: details.reason, gates };
  }
  if (details.killed === true) {
    return {
      reason:
        "CBC was still running after the hard deadline and was terminated. It had not returned Optimal.",
      gates,
    };
  }
  if (typeof details.status === "string" && STATUS_REASON[details.status]) {
    return { reason: STATUS_REASON[details.status], gates };
  }
  return { reason: problem.message, gates };
}
