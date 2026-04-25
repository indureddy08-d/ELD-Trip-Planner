import { Trash2, CheckCircle, AlertTriangle, XCircle } from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

const city = (s) => s.split(",")[0].trim();

function relativeTime(isoString) {
  const diff  = Date.now() - new Date(isoString).getTime();
  const mins  = Math.floor(diff / 60_000);
  const hours = Math.floor(diff / 3_600_000);
  const days  = Math.floor(diff / 86_400_000);
  if (mins  <  1) return "just now";
  if (mins  < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

// ── Compliance config ─────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  compliant: { Icon: CheckCircle, label: "Compliant",          color: "var(--c-success)", border: "var(--c-success)" },
  warning:   { Icon: AlertTriangle, label: "Compliant — Cycle Low", color: "var(--c-warn)",    border: "var(--c-warn)"    },
  illegal:   { Icon: XCircle,      label: "Not Legal to Begin", color: "var(--c-danger)",  border: "var(--c-danger)"  },
};

// ── Planner markers — what the engine inserted ────────────────────────────────
// Shown as compact tags. Only rendered when count > 0.

function Markers({ markers }) {
  if (!markers) return null;
  const tags = [];
  if (markers.breaks    > 0) tags.push({ key: "break",   label: markers.breaks    > 1 ? `${markers.breaks} breaks`   : "Break"   });
  if (markers.sleepers  > 0) tags.push({ key: "sleeper", label: markers.sleepers  > 1 ? `${markers.sleepers} sleepers` : "Sleeper" });
  if (markers.fuelStops > 0) tags.push({ key: "fuel",    label: markers.fuelStops > 1 ? `${markers.fuelStops} fuel stops` : "Fuel stop" });
  if (!tags.length) return null;
  return (
    <div className="rt-markers">
      {tags.map((t) => (
        <span key={t.key} className={`rt-marker rt-marker-${t.key}`}>{t.label}</span>
      ))}
    </div>
  );
}

// ── Single trip card — compact list item ─────────────────────────────────────
// Shows only what's needed to identify the trip and decide whether to open it.
// Full details (HOS duration, cycle remaining, stop count) live in the modal.

function TripCard({ trip, onLoad }) {
  const { form, summary, complianceStatus, markers, savedAt } = trip;
  const cfg = STATUS_CONFIG[complianceStatus] ?? STATUS_CONFIG.compliant;
  const { Icon, label: statusLabel, color: statusColor, border: borderColor } = cfg;

  return (
    <button
      type="button"
      className="rt-card"
      style={{ "--rt-border": borderColor }}
      onClick={() => onLoad(trip)}
    >
      {/* ── Row 1: origin → destination + timestamp ── */}
      <div className="rt-card-top">
        <span className="rt-headline">
          <span className="rt-origin">{city(form.current_location)}</span>
          <span className="rt-arrow">→</span>
          <span className="rt-dest">{city(form.dropoff_location)}</span>
        </span>
        <span className="rt-time">{relativeTime(savedAt)}</span>
      </div>

      {/* ── Row 2: via pickup + distance · days ── */}
      <div className="rt-card-mid">
        <span className="rt-via">via {city(form.pickup_location)}</span>
        <span className="rt-stats">
          {Math.round(summary.total_distance_miles).toLocaleString()} mi
          <span className="rt-dot">·</span>
          {summary.number_of_days} day{summary.number_of_days !== 1 ? "s" : ""}
        </span>
      </div>

      {/* ── Row 3: compliance status + optional planner badges ── */}
      <div className="rt-card-bot">
        <span className="rt-status" style={{ color: statusColor }}>
          <Icon size={10} strokeWidth={2.5} />
          {statusLabel}
        </span>
        <Markers markers={markers} />
      </div>
    </button>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function RecentTrips({ trips, onLoad, onClear, inline = false }) {
  if (!trips?.length) return null;

  return (
    <div className={`rt-root ${inline ? "rt-root-inline" : ""}`}>
      <div className="rt-header">
        <span className="rt-label">Recent trips</span>
        <button
          type="button"
          className="rt-clear"
          onClick={onClear}
          title="Clear trip history"
          aria-label="Clear trip history"
        >
          <Trash2 size={11} />
        </button>
      </div>

      <div className="rt-list">
        {trips.map((trip) => (
          <TripCard key={trip.id} trip={trip} onLoad={onLoad} />
        ))}
      </div>
    </div>
  );
}
