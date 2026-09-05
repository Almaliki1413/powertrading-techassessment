import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { App } from "./App";

vi.mock("react-plotly.js", () => ({
  default: () => <div data-testid="plot" />,
}));

const config = {
  benchmark_label: "Perfect-hindsight benchmark—not a live trading forecast.",
  pinned_range: { start_date: "2026-08-26", end_date: "2026-09-01", default_date: "2026-08-26" },
  battery: { capacity_mwh: "200" },
};

const resolved = {
  dataset_id: "sha256:abc",
  days: [
    {
      date: "2026-08-26",
      status: "validated",
      selectable: true,
      interval_count: 288,
      rrp_min: "-2.0",
      rrp_max: "161.21945",
      blocking_code: null,
      blocking_message: null,
    },
    {
      date: "2026-09-01",
      status: "blocking",
      selectable: false,
      interval_count: null,
      rrp_min: null,
      rrp_max: null,
      blocking_code: "HASH_MISMATCH",
      blocking_message: "unverified",
    },
  ],
};

function mockJson(data: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(data) } as Response);
}

describe("App states", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo) => {
        const url = String(input);
        if (url.includes("/config")) return mockJson(config);
        if (url.includes("/resolve")) return mockJson(resolved);
        return mockJson({});
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the benchmark banner visible", async () => {
    render(<App />);
    expect(
      await screen.findByText("Perfect-hindsight benchmark—not a live trading forecast."),
    ).toBeInTheDocument();
  });

  it("does not fabricate results in the ready/empty state", async () => {
    render(<App />);
    expect(await screen.findByText(/Awaiting verified schedule/)).toBeInTheDocument();
    expect(screen.queryByTestId("metric-revenue")).not.toBeInTheDocument();
  });

  it("disables optimization for an unvalidated day", async () => {
    const user = userEvent.setup();
    render(<App />);
    const select = await screen.findByLabelText("Selected calendar day");
    await user.selectOptions(select, "2026-09-01");
    expect(screen.getByRole("button", { name: /Run perfect-hindsight benchmark/ })).toBeDisabled();
    expect(screen.getByText(/Previous results cleared/)).toBeInTheDocument();
  });

  it("keeps Run disabled after date change while a solve is in flight", async () => {
    const twoDays = {
      dataset_id: "sha256:abc",
      days: [
        { ...resolved.days[0] },
        {
          date: "2026-08-27",
          status: "validated",
          selectable: true,
          interval_count: 288,
          rrp_min: "0",
          rrp_max: "100",
          blocking_code: null,
          blocking_message: null,
        },
      ],
    };
    const staleResult = {
      request_id: "req-1",
      dataset_hash: "sha256:abc",
      config_hash: "sha256:cfg",
      selected_date: "2026-08-26",
      benchmark_label: config.benchmark_label,
      battery: config.battery,
      solver: {
        pulp_version: "3.3.2",
        cbc_version: "2.10.3",
        executable_path: "cbc",
        executable_sha256: null,
        options: ["threads=1"],
      },
      metrics: {
        gross_simulated_revenue_aud: "24973",
        imported_mwh: "10",
        exported_mwh: "10",
        throughput_mwh: "20",
        equivalent_full_cycles: "0.1",
        ending_soc_mwh: "100",
        idle_preference_objective: "0",
        solve_wall_time_s: 1,
        verification_passed: true,
      },
      decisions: [],
      verification: { passed: true, failures: [] },
      provenance: {},
      stage_evidence: [],
    };
    let finishSolve: (value: Response) => void = () => undefined;
    const hangingSolve = new Promise<Response>((resolve) => {
      finishSolve = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo) => {
        const url = String(input);
        if (url.includes("/config")) return mockJson(config);
        if (url.includes("/resolve")) return mockJson(twoDays);
        if (url.includes("/optimizations")) return hangingSolve;
        return mockJson({});
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    const run = await screen.findByRole("button", { name: /Run perfect-hindsight benchmark/ });
    await waitFor(() => expect(run).toBeEnabled());
    await user.click(run);
    expect(await screen.findByRole("button", { name: /Solving/ })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Selected calendar day"), "2026-08-27");
    expect(screen.getByRole("button", { name: /Solving/ })).toBeDisabled();
    finishSolve({ ok: true, json: () => Promise.resolve(staleResult) } as Response);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Run perfect-hindsight benchmark/ })).toBeEnabled();
    });
    expect(screen.queryByTestId("metric-revenue")).not.toBeInTheDocument();
    expect(screen.getByText(/Run again for the selected day/)).toBeInTheDocument();
  });

  it("shows which solve gate failed and why stage 2 was not Optimal", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo) => {
        const url = String(input);
        if (url.includes("/config")) return mockJson(config);
        if (url.includes("/resolve")) return mockJson(resolved);
        if (url.includes("/optimizations")) {
          return Promise.resolve({
            ok: false,
            json: () =>
              Promise.resolve({
                code: "SOLVER_FAILED",
                message: "CBC stage 2 did not return Optimal",
                blocking: true,
                request_id: "req-stage-2",
                details: { stage: 2, status: "Not Solved", wall_time_s: 30.1 },
              }),
          } as Response);
        }
        return mockJson({});
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    const run = await screen.findByRole("button", { name: /Run perfect-hindsight benchmark/ });
    await waitFor(() => expect(run).toBeEnabled());
    await user.click(run);
    expect(await screen.findByText(/CBC stage 2 — minimize throughput/)).toBeInTheDocument();
    expect(screen.getByText(/Failed/)).toBeInTheDocument();
    expect(screen.getByText(/before proving optimality/)).toBeInTheDocument();
    expect(screen.getByText(/CBC status: Not Solved/)).toBeInTheDocument();
  });
});
