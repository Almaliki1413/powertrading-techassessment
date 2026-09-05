import { render, screen } from "@testing-library/react";
import type { Decision } from "../../api/contracts";
import { IntervalAuditTable } from "./IntervalAuditTable";

const decision: Decision = {
  interval_end: "2026-08-26T00:05:00+10:00",
  rrp_aud_per_mwh: "89.76213",
  action: "charge",
  signed_power_mw: "-100",
  imported_mwh: "8.333",
  exported_mwh: "0",
  soc_before_mwh: "100",
  soc_after_mwh: "107.9",
  interval_cash_flow_aud: "-748.02",
  cumulative_cash_flow_aud: "-748.02",
  reason_code: "BOUND_POWER",
  reason_text:
    "Charge reaches the 100 MW power limit. Idle is infeasible with later intervals held fixed: the 100 MWh terminal target would be missed.",
  binding_constraints: ["power_limit"],
  price_percentile: "40",
};

it("shows the contrast sentence in the audit table, not only as a tooltip", () => {
  render(<IntervalAuditTable decisions={[decision]} />);
  expect(screen.getByText(/Idle is infeasible with later intervals held fixed/)).toBeInTheDocument();
});
