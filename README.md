# NSW1 BESS — Perfect-hindsight benchmark

**Perfect-hindsight benchmark—not a live trading forecast.**

This repository is a locally runnable modular monolith. It verifies authentic AEMO DispatchIS archives, extracts five-minute `NSW1` `RRP`, and solves a 200 MWh / 100 MW battery schedule with PuLP/CBC. The UI shows prices, signed power, SoC, gross simulated cash flow, reasons, assumptions, quality, and provenance.

## First screen

The trader view keeps a persistent hindsight warning, a pinned-data quality strip, headline metrics (gross AUD, ending SoC, import/export MWh, throughput/cycles, solver/verification status), four synchronized Plotly charts, an interval audit table, and expandable assumptions/provenance/limitations. Charts and the table appear only after an independently verified solve. The UI never fabricates demo output.

## 30-minute review map

Open these files in order:

- `backend/app/infrastructure/aemo/dispatchis_parser.py` — AEMO C/I/D parse and NSW1 `RRP`
- `backend/app/domain/battery.py` and `backend/app/domain/revenue.py` — MW↔MWh, SoC, cash flow
- `backend/app/infrastructure/optimization/pulp_cbc.py` and `backend/app/domain/verification.py` — three-stage solve and independent check
- `backend/app/domain/explanations.py` — reason codes and local contrast
- `frontend/src/app/App.tsx` — trader blotter

## Prerequisites

- Python 3.13
- Node.js 22 and npm
- The inspected archive `data/pinned/PUBLIC_DISPATCHIS_20260826.zip` (SHA-256 `f9f389839f2ea704770fa736ef85e014a2cc5ab2ef5f4dcb363e70d1f70d22fb`)

CBC is the solver bundled with PuLP (`PULP_CBC_CMD`). Exact versions are written to `build-info.json` by `scripts/record_versions.py`, which queries the CBC executable rather than guessing from the PuLP package name.

## Quick start

From the repository root:

```bash
python scripts/make.py bootstrap
python scripts/make.py dev
```

- API: http://127.0.0.1:8000
- UI:  http://127.0.0.1:5173 (also http://localhost:5173)

On Windows, `make.cmd bootstrap` is equivalent. GNU `make` targets wrap the same Python runner.

Production-shaped local serving (FastAPI + built React):

```bash
python scripts/make.py build
python scripts/make.py run
```

Then open http://127.0.0.1:8000

## Data source and provenance

- Source: AEMO NEMWEB DispatchIS archive directory `https://nemweb.com.au/Reports/Archive/DispatchIS_Reports/`
- Pinned range: `2026-08-26` through `2026-09-01`
- All seven daily archives are now inspected, hash-pinned, and quality-gated (288 NSW1 intervals each)
- Default / walkthrough day is `2026-08-26` because that day completes the three-stage CBC solve under the documented timeout. Other pinned days stay selectable after the same data gates, but stage 2 may time out; the UI then shows no schedule.
- Synthetic prices are never substituted. A day stays unselectable if its bytes or quality report fail.

`python scripts/make.py verify-data` re-runs ZIP safety, dynamic C/I/D parsing, NSW1 completeness, and hash checks for every file marked `passed`.

## Architecture

```
frontend (React/TS) → FastAPI /api/v1
FastAPI → application services → domain
infrastructure adapters → AEMO ZIP/parser, PuLP/CBC, content-addressed cache
```

- `backend/app/domain` is stdlib-only (battery, cash flow, verifier, reasons).
- `backend/app/application` orchestrates resolve/validate/solve and does not hide domain errors.
- `backend/app/infrastructure` owns archive acquisition, ZIP safety, DispatchIS parsing, and CBC.
- The frontend performs no battery, revenue, deduplication, or provenance calculations.

## Battery equations and signs

- Interval energy: `MWh = MW × 5/60`
- SoC: `SoC_{t+1} = SoC_t + η_c charge_t Δt − discharge_t Δt / η_d`
- `η_c = η_d = √0.90`
- Cash flow: `RRP_t × (discharge_t − charge_t) × Δt` (no price-sign branch)
- Export/discharge power is positive; import/charge is negative; positive cash flow is revenue
- Initial and terminal SoC: 100 MWh; bounds 0–200 MWh; power 100 MW / 100 MW
- Gross energy-market cash flow only (no FCAS, fees, degradation, or market impact)

## Optimization and tie-break

1. Maximize total signed revenue; require CBC `Optimal`; recompute `R*` independently.
2. Constrain revenue `≥ R* − 1e-6 AUD`; minimize throughput MWh; recompute `T*`.
3. Keep both bounds; minimize active charge/discharge binaries; extract the stage-3 schedule.
4. The independent verifier (no PuLP imports) must pass or the API returns `POST_SOLVE_VERIFICATION_FAILED`.

## UI interpretation

Reason codes name binding constraints. They must not be read as “a local threshold caused this MILP choice.” Beside each interval, the audit table also shows a local contrast: idle or the opposite action with every other interval held fixed. That sentence answers why this interval was not left idle or reversed. Idle after stages 2–3 is `IDLE_TIE_BREAK` or `IDLE_GLOBAL_OPTIMUM`.

## Choices and trade-offs

- **MILP vs a percentile heuristic.** A “charge the cheapest 30% / discharge the richest 30%” rule is easy to explain and wrong on this battery: SoC, round-trip efficiency, and the 100 MWh terminal couple the day. The MILP maximises signed cash flow under those constraints. Cost: some pinned days may not prove stage 2 inside the documented timeout. The app fails closed rather than publishing a heuristic and calling it optimal.
- **Terminal SoC 100 vs free-end.** Free-end treats leftover energy as worthless and inflates one-day revenue by draining the pack. 100 MWh in and out makes the day a like-for-like cycle. Cost: the last intervals can charge at a high price just to hit 100 MWh. That looks locally wasteful and is a feature of the assumption.
- **Three stages vs one objective.** One `max revenue` solve can chatter: same money, extra cycling. Stage 2 picks the least-throughput schedule at `R*`. Stage 3 prefers idle among those ties so the blotter is readable. Cost: stage 2 is the slow MIP and the usual 1 Sep-style failure mode.

## Tests and known checks

```bash
python scripts/make.py test
python scripts/make.py verify-data
```

Known inspected-day fixture: 288 NSW1 rows, RRP from `-2.0` to `161.21945`, interval ends `2026-08-26 00:05` through `2026-08-27 00:00` NEM market time (`Australia/Brisbane`, AEST UTC+10 year-round).

## Limitations, failures, and roadmap

- Fail-closed: missing intervals, invalid RRP, unsafe ZIP, hash mismatch, non-optimal CBC, or verification failure produce no trader result.
- Authentication, durable tenants, live bidding, and no-hindsight forecasting are explicitly out of scope.
- The pinned seven-day range is approved after the same inspection as `2026-08-26`. Re-run `python scripts/make.py verify-data` after replacing any archive.
- Production evolution: durable job history, stronger observability, and a causal (non-hindsight) policy — none of that is claimed here.

## Four-hour scope

The polished vertical slice is authentic `2026-08-26` bytes → safe parser → 288 NSW1 prices → three-stage MILP → independent verifier → trader UI + README. Optional no-hindsight work is not included and must not displace this core.
