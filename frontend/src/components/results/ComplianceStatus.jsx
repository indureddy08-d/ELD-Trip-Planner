import { CheckCircle, AlertTriangle, XCircle, Coffee, BedDouble, Fuel } from "lucide-react";

// ── Status derivation ─────────────────────────────────────────────────────────

function deriveStatus(warnings, summary) {
  if (summary.cycle_hours_remaining === 0) return "illegal";
  if (warnings?.some((w) => w.code === "CYCLE_EXCEEDED")) return "illegal";
  if (warnings?.some((w) => w.code === "CYCLE_LOW")) return "warning";
  return "compliant";
}

// ── Planner actions — what the HOS engine scheduled ──────────────────────────

function deriveActions(stops) {
  const actions = [];

  const restCount    = stops.filter((s) => s.stop_type === "rest").length;
  const sleeperCount = stops.filter((s) => s.stop_type === "sleeper").length;
  const fuelCount    = stops.filter((s) => s.stop_type === "fuel").length;

  if (restCount > 0) {
    actions.push({
      id: "rest",
      Icon: Coffee,
      label: restCount === 1 ? "Break" : `${restCount}× Break`,
      full:  restCount === 1 ? "30-min break scheduled" : `${restCount} mandatory breaks scheduled`,
      title: "30-min off-duty break · 8h driving rule · 49 CFR 395.3",
      colorVar: "var(--c-warn)",
      bgVar:    "rgba(232,150,10,.1)",
    });
  }

  if (sleeperCount > 0) {
    actions.push({
      id: "sleeper",
      Icon: BedDouble,
      label: sleeperCount === 1 ? "Sleeper" : `${sleeperCount}× Sleeper`,
      full:  sleeperCount === 1 ? "Sleeper Berth (10h) scheduled" : `${sleeperCount} sleeper berths scheduled`,
      title: "Sleeper Berth (10h) · resets 11h driving & 14h on-duty windows",
      colorVar: "var(--c-purple)",
      bgVar:    "rgba(124,92,232,.1)",
    });
  }

  if (fuelCount > 0) {
    actions.push({
      id: "fuel",
      Icon: Fuel,
      label: fuelCount === 1 ? "Fuel" : `${fuelCount}× Fuel`,
      full:  fuelCount === 1 ? "Fuel stop planned" : `${fuelCount} fuel stops planned`,
      title: "Fuel stop · required every 1,000 mi",
      colorVar: "var(--c-danger)",
      bgVar:    "rgba(224,62,62,.1)",
    });
  }

  return actions;
}

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  compliant: { Icon: CheckCircle,  label: "HOS Compliant",       cls: "cs-status-compliant" },
  warning:   { Icon: AlertTriangle, label: "Compliant — Cycle Low", cls: "cs-status-warning"  },
  illegal:   { Icon: XCircle,      label: "Not Legal to Begin",  cls: "cs-status-illegal"   },
};

// ── Main component ────────────────────────────────────────────────────────────
//
// Layout: one horizontal band.
//   Left  — status badge (always visible)
//   Right — action chips (one per planner intervention, colored by type)
//           or "No additional stops" when the trip is clean
//
// The badge and chips read as one status line, not two separate sections.

export default function ComplianceStatus({ warnings, stops, summary }) {
  const status  = deriveStatus(warnings, summary);
  const actions = deriveActions(stops);
  const { Icon, label, cls } = STATUS_CONFIG[status];

  return (
    <div className="cs-root">

      {/* Status badge */}
      <div className={`cs-badge ${cls}`}>
        <Icon size={13} strokeWidth={2.5} className="cs-badge-icon" />
        <span className="cs-badge-label">{label}</span>
      </div>

      {/* Action chips — colored by type, tooltip carries the detail */}
      {actions.length > 0 && (
        <div className="cs-chips">
          {actions.map((action) => (
            <span
              key={action.id}
              className="cs-chip"
              style={{ color: action.colorVar, background: action.bgVar }}
              title={action.title}
            >
              <action.Icon size={10} strokeWidth={2} />
              {action.full}
            </span>
          ))}
        </div>
      )}

      {/* Clean trip — no interventions */}
      {actions.length === 0 && status === "compliant" && (
        <span className="cs-clean">No additional stops required</span>
      )}

    </div>
  );
}
