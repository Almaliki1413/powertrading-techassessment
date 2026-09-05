import type { DaySummary, OptimizationResult, ProblemDetails } from "./contracts";

async function parse<T>(response: Response): Promise<T> {
  const body = await response.json();
  if (!response.ok) {
    throw body as ProblemDetails;
  }
  return body as T;
}

export async function fetchConfig() {
  return parse<{
    benchmark_label: string;
    pinned_range: { start_date: string; end_date: string; default_date: string };
    battery: Record<string, string>;
  }>(await fetch("/api/v1/config"));
}

export async function fetchPinned() {
  return parse<{
    default_date: string;
    files: Array<{ dispatch_date: string; inspection_status: string; sha256: string | null }>;
  }>(await fetch("/api/v1/datasets/pinned"));
}

export async function resolveDataset(start: string, end: string, sourceMode: string) {
  return parse<{ dataset_id: string; days: DaySummary[] }>(
    await fetch("/api/v1/datasets/resolve", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ start_date: start, end_date: end, source_mode: sourceMode }),
    }),
  );
}

export async function runOptimization(datasetId: string, selectedDate: string) {
  return parse<OptimizationResult>(
    await fetch("/api/v1/optimizations", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        dataset_id: datasetId,
        selected_date: selectedDate,
        mode: "independent_day",
      }),
    }),
  );
}
