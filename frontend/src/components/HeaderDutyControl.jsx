import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Clock } from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(date) {
  if (!date) return "—";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtElapsed(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function fmtHours(h) {
  if (h === null || h === undefined) return "—";
  let hrs  = Math.floor(h);
  let mins = Math.round((h - hrs) * 60);
  // Normalize: if minutes round to 60, roll into hours
  if (mins === 60) { hrs += 1; mins = 0; }
  if (hrs === 0) return `${mins}m`;
  if (mins === 0) return `${hrs}h`;
  return `${hrs}h ${mins}m`;
}

// ── Toggle switch ─────────────────────────────────────────────────────────────

function DutyToggle({ active, onToggle }) {
  return (
    <button
      role="switch"
      aria-checked={active}
      onClick={onToggle}
      className={`hdc-toggle ${active ? "hdc-toggle-on" : ""}`}
      title={active ? "End duty session" : "Start duty session"}
    >
      <span className="hdc-toggle-thumb" />
    </button>
  );
}

// ── Gauge bar ─────────────────────────────────────────────────────────────────

function GaugeBar({ value, max, warnBelow, color, frozen }) {
  const pct  = Math.min(100, (value / max) * 100);
  const warn = !frozen && value <= warnBelow;
  return (
    <div className="hdc-gauge-track">
      <div
        className="hdc-gauge-fill"
        style={{
          width: `${pct}%`,
          background: frozen ? "var(--c-border)" : warn ? "var(--c-danger)" : color,
          transition: frozen ? "none" : undefined,
        }}
      />
    </div>
  );
}

// ── Timing row ────────────────────────────────────────────────────────────────

function TimingRow({ label, value, color, warnBelow, max, frozen }) {
  const warn = !frozen && value !== null && value <= warnBelow;
  return (
    <div className={`hdc-timing-row ${warn ? "hdc-timing-warn" : ""}`}>
      <span className="hdc-timing-label">{label}</span>
      <span
        className="hdc-timing-value"
        style={{ color: frozen ? "var(--c-muted)" : warn ? "var(--c-danger)" : color }}
      >
        {fmtHours(value)}
      </span>
      {max && (
        <GaugeBar value={value} max={max} warnBelow={warnBelow} color={color} frozen={frozen} />
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function HeaderDutyControl({ session }) {
  const {
    status, startedAt, endedAt, now, elapsed,
    remainingOnDuty, remainingDriving,
    startDuty, endDuty, resetDuty,
  } = session;

  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const isActive = status === "active";
  const isEnded  = status === "ended";
  const isIdle   = status === "idle";

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Toggle: idle/ended → start; active → end
  function handleToggle() {
    if (isActive) endDuty();
    else startDuty();
  }

  return (
    <div className="hdc-root" ref={ref}>

      {/* ── Pill button ── */}
      {/* Styled like the history button — bordered, compact, secondary.    */}
      {/* Clicking the pill body opens the panel; toggle starts/stops duty. */}
      <div
        className={`hdc-pill ${open ? "hdc-pill-open" : ""} ${isActive ? "hdc-pill-active" : ""}`}
        role="group"
        aria-label="Session Tracker"
      >

        {/* Status dot — only visible when active */}
        {isActive && <span className="hdc-dot" aria-hidden="true" />}

        {/* Label — always "Session Tracker" */}
        <span className="hdc-label">Session Tracker</span>

        {/* Separator */}
        <span className="hdc-sep" aria-hidden="true">·</span>

        {/* Status text */}
        <span className={`hdc-status-text ${isActive ? "hdc-status-on" : isEnded ? "hdc-status-ended" : ""}`}>
          {isActive ? "On Duty" : isEnded ? "Ended" : "Off Duty"}
        </span>

        {/* Drive/Duty remaining — only when active, hidden on small screens */}
        {isActive && (
          <span className="hdc-status-detail" aria-label={`Drive ${fmtHours(remainingDriving)}, Duty ${fmtHours(remainingOnDuty)} remaining`}>
            · Drive: {fmtHours(remainingDriving)} · Duty: {fmtHours(remainingOnDuty)}
          </span>
        )}

        {/* Toggle — start/stop affordance */}
        <DutyToggle active={isActive} onToggle={handleToggle} />

        {/* Chevron — opens detail panel */}
        <button
          className="hdc-chevron-btn"
          onClick={() => setOpen((o) => !o)}
          aria-label={open ? "Close session details" : "Open session details"}
          aria-expanded={open}
          aria-haspopup="true"
        >
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>

      </div>

      {/* ── Detail panel ── */}
      {open && (
        <div className="hdc-panel" role="dialog" aria-label="Session Tracker details">

          {/* Panel header */}
          <div className="hdc-panel-header">
            <span className="hdc-panel-title">Session Tracker</span>
            <span className="hdc-panel-note">
              Optional live timer — separate from trip planning and ELD generation
            </span>
          </div>

          {/* Idle state */}
          {isIdle && (
            <div className="hdc-panel-idle">
              Use the toggle to start tracking your on-duty time.
            </div>
          )}

          {/* Active / ended body */}
          {!isIdle && (
            <div className="hdc-panel-body">

              <div className="hdc-clock-grid">
                <div className="hdc-clock-cell">
                  <span className="hdc-clock-label">Started</span>
                  <span className="hdc-clock-value">{fmtTime(startedAt)}</span>
                </div>
                <div className="hdc-clock-cell">
                  <span className="hdc-clock-label">{isActive ? "Now" : "Ended"}</span>
                  <span
                    className="hdc-clock-value hdc-clock-mono"
                    style={{ color: isEnded ? "var(--c-muted)" : "var(--c-success)" }}
                  >
                    {fmtTime(isActive ? now : endedAt)}
                  </span>
                </div>
                <div className="hdc-clock-cell">
                  <span className="hdc-clock-label">{isActive ? "Elapsed" : "Duration"}</span>
                  <span
                    className="hdc-clock-value hdc-clock-mono"
                    style={{ color: isEnded ? "var(--c-muted)" : "var(--c-success)" }}
                  >
                    {fmtElapsed(elapsed)}
                  </span>
                </div>
              </div>

              {isEnded && (
                <div className="hdc-frozen-note">
                  <Clock size={11} /> Counters frozen at session end
                </div>
              )}

              <div className="hdc-section-label">HOS Window Remaining</div>
              <TimingRow
                label="14h On-Duty Window"
                value={remainingOnDuty}
                color="var(--c-accent)"
                warnBelow={2}
                max={14}
                frozen={isEnded}
              />
              <TimingRow
                label="11h Driving Limit"
                value={remainingDriving}
                color="var(--c-success)"
                warnBelow={1}
                max={11}
                frozen={isEnded}
              />

            </div>
          )}

          {isEnded && (
            <div className="hdc-panel-footer">
              <button className="hdc-reset-btn" onClick={() => { resetDuty(); setOpen(false); }}>
                Start New Session
              </button>
            </div>
          )}

        </div>
      )}
    </div>
  );
}
