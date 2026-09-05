import type { DaySummary } from "../../api/contracts";

type Props = {
  sourceMode: string;
  days: DaySummary[];
  selectedDate: string;
  onDateChange: (value: string) => void;
  onSolve: () => void;
  solving: boolean;
  canSolve: boolean;
};

function weekday(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-AU", {
    weekday: "short",
    timeZone: "UTC",
  });
}

function shortDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-AU", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

function priceEnvelope(day: DaySummary): string | null {
  if (day.rrp_min == null || day.rrp_max == null) return null;
  const min = Number(day.rrp_min);
  const max = Number(day.rrp_max);
  if (!Number.isFinite(min) || !Number.isFinite(max)) return `${day.rrp_min}–${day.rrp_max}`;
  return `${Math.round(min)}–${Math.round(max)} AUD`;
}

export function DatasetToolbar({
  sourceMode,
  days,
  selectedDate,
  onDateChange,
  onSolve,
  solving,
  canSolve,
}: Props) {
  const selected = days.find((day) => day.date === selectedDate);
  const qualityClass = selected?.selectable ? "ok" : selected ? "bad" : "warn";
  const qualityLabel = selected?.selectable
    ? "Validated — 288 NSW1 intervals"
    : selected?.blocking_code ?? "No validated day";

  return (
    <section className="toolbar" aria-label="Dataset controls">
      <div className="day-rail">
        {days.map((day) => {
          const envelope = priceEnvelope(day);
          return (
            <button
              key={day.date}
              type="button"
              className={[
                "day-chip",
                day.date === selectedDate ? "is-selected" : "",
                day.selectable ? "is-ok" : "is-blocked",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => onDateChange(day.date)}
              aria-pressed={day.date === selectedDate}
              aria-label={`${day.date}${day.selectable ? " validated" : ` ${day.status}`}`}
            >
              <span className="day-chip-wd">{weekday(day.date)}</span>
              <span className="day-chip-dt">{shortDate(day.date)}</span>
              <span className="day-chip-meta">
                {day.selectable ? "288 firm" : day.blocking_code ?? day.status}
                {envelope ? ` · ${envelope}` : null}
              </span>
            </button>
          );
        })}
      </div>
      <div className="toolbar-row">
        <div className="toolbar-meta">
          <div className="field">
            Source
            <span className="badge">{sourceMode}</span>
          </div>
          <label className="field">
            Selected calendar day (NEM market time)
            <select
              value={selectedDate}
              onChange={(event) => onDateChange(event.target.value)}
              aria-label="Selected calendar day"
            >
              {days.map((day) => (
                <option key={day.date} value={day.date}>
                  {day.date}
                  {day.selectable ? " — validated" : ` — ${day.status}`}
                </option>
              ))}
            </select>
          </label>
          <div className="field">
            Data quality
            <span className={`badge ${qualityClass}`}>{qualityLabel}</span>
          </div>
        </div>
        <button
          className={`primary${solving ? " is-busy" : ""}`}
          type="button"
          onClick={onSolve}
          disabled={!canSolve || solving}
        >
          {solving ? "Solving…" : "Run perfect-hindsight benchmark"}
        </button>
      </div>
    </section>
  );
}
