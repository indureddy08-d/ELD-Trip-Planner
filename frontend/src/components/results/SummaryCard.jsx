import { AlertTriangle, ChevronDown, ChevronUp, Info } from "lucide-react";
import { useState } from "react";
import { formatHours, formatMiles } from "../../utils/formatters";
import ComplianceStatus from "./ComplianceStatus";

const WARNING_SEVERITY = {
  CYCLE_EXCEEDED:     "danger",
  CYCLE_LOW:          "warn",
  DISTANCE_ESTIMATED: "warn",
  MULTI_DAY_TRIP:     "info",
  HIGH_FUEL_STOPS:    "info",
};

// ── Human-readable labels for assumption codes ────────────────────────────────
// Maps internal planner codes to short, plain-English labels.
// Codes not in this map fall back to a title-cased version of the code.

const ASSUMPTION_LABELS = {
  DRIVER_TYPE:        "Driver type",
  CYCLE:              "HOS cycle",
  ADVERSE_CONDITIONS: "Adverse conditions",
  AVERAGE_SPEED:      "Speed estimate",
  PICKUP_DROPOFF:     "Pickup & dropoff",
  FUEL_INTERVAL:      "Fuel interval",
  BREAK_MODEL:        "Mandatory break",
  FUEL_BREAK_RESET:   "Fuel break reset",
  SPLIT_SB:           "Split sleeper berth",
  ROUTING_PROVIDER:   "Distance source",
};

function humanLabel(code) {
  return ASSUMPTION_LABELS[code] ?? code.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

// ── Warning banner ────────────────────────────────────────────────────────────

function WarningBanner({ warnings }) {
  if (!warnings?.length) return null;
  return (
    <div className="notices-group">
      {warnings.map((w) => {
        const sev = WARNING_SEVERITY[w.code] || "warn";
        return (
          <div key={w.code} className={`notice-item notice-${sev}`}>
            <AlertTriangle size={14} className="notice-icon" />
            <span>{w.message}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Assumptions footnote ──────────────────────────────────────────────────────
//
// Default state: a one-line summary of the three most important assumptions
// (speed, cycle, adverse conditions) so reviewers can verify at a glance.
//
// Expanded state: a clean two-column list — human label on the left,
// plain-text value on the right. No code badges, no debug table.

const KEY_ASSUMPTIONS = ["AVERAGE_SPEED", "CYCLE", "ADVERSE_CONDITIONS"];

function Footnote({ assumptions }) {
  const [expanded, setExpanded] = useState(false);

  if (!assumptions?.length) return null;

  // Build a quick-access map for the summary line
  const byCode = Object.fromEntries(assumptions.map(a => [a.code, a.message]));

  // Extract speed value — handle both integer (55) and float (55.0) formats
  const speedMsg = byCode["AVERAGE_SPEED"] ?? "";
  const speedMatch = speedMsg.match(/(\d+(?:\.\d+)?)\s*mph/);
  const speedVal = speedMatch
    ? `${parseFloat(speedMatch[1]) % 1 === 0 ? parseInt(speedMatch[1], 10) : speedMatch[1]} mph`
    : null;

  return (
    <div className="summary-footnote">
      <div className="summary-footnote-bar">
        {/* Summary line — key facts visible without expanding */}
        <span className="summary-footnote-text">
          <Info size={11} style={{ display: "inline", verticalAlign: "middle", marginRight: 5, opacity: .5 }} />
          Property-carrying · 70h/8-day cycle
          {speedVal && <> · {speedVal} fixed speed</>}
          {" · "}No adverse conditions
        </span>
        <button
          className="summary-footnote-toggle"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          <span className="summary-footnote-toggle-label">Planning assumptions</span>
          {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        </button>
      </div>

      {expanded && (
        <ul className="assump-detail-list">
          {assumptions.map((a) => (
            <li key={a.code} className="assump-detail-row">
              <span className="assump-detail-label">{humanLabel(a.code)}</span>
              <span className="assump-detail-msg">{a.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SummaryCard({ summary, warnings, assumptions, stops }) {
  const cycleRemaining = summary.cycle_hours_remaining;
  const cycleWarn = cycleRemaining < 10;

  return (
    <div className="summary-card">

      {/* ── Compliance block — status + warnings grouped together ── */}
      <div className="summary-compliance-group">
        <ComplianceStatus warnings={warnings} stops={stops} summary={summary} />
        <WarningBanner warnings={warnings} />
      </div>

      {/* ── Primary metrics — large, fast to scan ── */}
      <div className="summary-primary">
        <div className="summary-primary-item">
          <span className="summary-primary-value">
            {formatMiles(summary.total_distance_miles)}
          </span>
          <span className="summary-primary-label">Total Distance</span>
        </div>
        <div className="summary-primary-divider" />
        <div className="summary-primary-item">
          <span className="summary-primary-value">
            {summary.number_of_days} day{summary.number_of_days !== 1 ? "s" : ""}
          </span>
          <span className="summary-primary-label">On Road</span>
        </div>
        <div className="summary-primary-divider" />
        <div className="summary-primary-item">
          <span className={`summary-primary-value ${cycleWarn ? "summary-primary-warn" : ""}`}>
            {formatHours(Math.max(0, cycleRemaining))}
          </span>
          <span className="summary-primary-label">Cycle Remaining</span>
        </div>
      </div>

      {/* ── Supporting metrics — two equal panels ── */}
      <div className="summary-detail">

        {/* Left panel: route breakdown */}
        <div className="summary-detail-col">
          <div className="summary-detail-heading">Route</div>
          <dl className="summary-detail-dl">
            <div className="summary-detail-row">
              <dt>Deadhead</dt>
              <dd>{formatMiles(summary.deadhead_miles)}</dd>
            </div>
            <div className="summary-detail-row">
              <dt>Loaded</dt>
              <dd>{formatMiles(summary.loaded_miles)}</dd>
            </div>
            <div className="summary-detail-row">
              <dt>Stops</dt>
              <dd>{summary.number_of_stops}</dd>
            </div>
          </dl>
        </div>

        <div className="summary-detail-divider" aria-hidden="true" />

        {/* Right panel: time & cycle */}
        <div className="summary-detail-col">
          <div className="summary-detail-heading">Hours &amp; Cycle</div>
          <dl className="summary-detail-dl">
            <div className="summary-detail-row">
              <dt>HOS Sim Time</dt>
              <dd>{formatHours(summary.estimated_total_hours)}</dd>
            </div>
            <div className="summary-detail-row">
              <dt>Route API Time</dt>
              <dd>{summary.provider_driving_hours ? formatHours(summary.provider_driving_hours) : "—"}</dd>
            </div>
            <div className={`summary-detail-row ${cycleWarn ? "summary-detail-warn" : ""}`}>
              <dt>After Trip</dt>
              <dd>{formatHours(summary.cycle_hours_used_after_trip)}</dd>
            </div>
          </dl>
        </div>

      </div>

      {/* ── Footnote — planning assumptions ── */}
      <Footnote assumptions={assumptions} />

    </div>
  );
}
