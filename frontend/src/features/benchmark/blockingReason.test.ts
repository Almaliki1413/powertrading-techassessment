import { describe, expect, it } from "vitest";
import { describeBlockingProblem } from "./blockingReason";

describe("describeBlockingProblem", () => {
  it("marks earlier gates passed and names a Not Solved stage 2", () => {
    const view = describeBlockingProblem({
      code: "SOLVER_FAILED",
      message: "CBC stage 2 did not return Optimal",
      blocking: true,
      request_id: "req-1",
      details: { stage: 2, status: "Not Solved", wall_time_s: 30.1 },
    });
    expect(view.gates.map((gate) => [gate.id, gate.state])).toEqual([
      ["dataset", "passed"],
      ["cbc_stage_1", "passed"],
      ["cbc_stage_2", "failed"],
      ["cbc_stage_3", "not_reached"],
      ["verifier", "not_reached"],
    ]);
    expect(view.reason).toMatch(/before proving optimality/);
  });

  it("explains a watchdog kill on stage 2", () => {
    const view = describeBlockingProblem({
      code: "SOLVER_FAILED",
      message: "CBC exceeded the hard deadline and was terminated",
      blocking: true,
      request_id: "req-2",
      details: { stage: 2, killed: true, deadline_s: 35 },
    });
    expect(view.gates.find((gate) => gate.id === "cbc_stage_2")?.state).toBe("failed");
    expect(view.reason).toMatch(/hard deadline/);
  });
});
