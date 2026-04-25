import { useEffect } from "react";
import {
  X, CheckCircle, AlertTriangle, XCircle,
  MapPin, Coffee, BedDouble, Fuel, ArrowRight, Trash2,
} from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtHours(h) {
  if (h == null) return "—";
  const hrs  = Math.floor(h);
  const mins = Math.round((h - hrs) * 60);
  if (hrs === 0) return `${mins}m`;
  if (mins === 0) return `${hrs}h`;
  return `${hrs}h ${mins}m`;
}

function fmtDate(isoString) {
  return new Date(isoString).toLocaleString([], {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ── Compliance config ─────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  compliant: { Icon: CheckCircle, label: "HOS Compliant",       color: "var(--c-success)" },
  warning:   { Icon: AlertTriangle, label: "Compliant — Cycle Low", color: "var(--c-warn)" },
  illegal:   { Icon: XCircle,      label: "Not Legal to Begin", color: "var(--c-danger)"  },
};

// ── Planner actions ───────────────────────────────────────────────────────────

function PlannerActions({ markers }) {
  if (!markers) return null;
  const actions = [];
  if (markers.breaks    > 0) actions.push({ Icon: Coffee,    color: "var(--c-warn)",   label: markers.breaks    === 1 ? "30-min break scheduled"                    : `${markers.breaks} mandatory breaks scheduled`    });
  if (markers.sleepers  > 0) actions.push({ Icon: BedDouble, color: "var(--c-purple)", label: markers.sleepers  === 1 ? "Sleeper Berth (10h) scheduled"              : `${markers.sleepers} sleeper berths scheduled`    });
  if (markers.fuelStops > 0) actions.push({ Icon: Fuel,      color: "var(--c-danger)", label: markers.fuelStops === 1 ? "Fuel stop planned"                         : `${markers.fuelStops} fuel stops planned`         });
  if (!actions.length) return null;

  return (
    <div className="tpm-section">
      <div className="tpm-section-label">Planner actions applied</div>
      <div className="tpm-actions">
        {actions.map((action, i) => {
          const ActionIcon = action.Icon;
          return (
            <div key={i} className="tpm-action-row">
              <ActionIcon size={12} strokeWidth={2} style={{ color: action.color, flexShrink: 0 }} />
              <span className="tpm-action-label">{action.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────

export default function TripPreviewModal({ trip, onLoad, onRemove, onClose }) {
  const { form, summary, complianceStatus, markers, savedAt } = trip;
  const cfg = STATUS_CONFIG[complianceStatus] ?? STATUS_CONFIG.compliant;
  const { Icon: StatusIcon, label: statusLabel, color: statusColor } = cfg;

  // Close on Escape
  useEffect(() => {
    function onKey(e) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Prevent body scroll while open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);

  return (
    <div className="tpm-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="tpm-card" onClick={(e) => e.stopPropagation()}>

        {/* ── Header ── */}
        <div className="tpm-header">
          <div className="tpm-header-left">
            <span className="tpm-title">Trip Preview</span>
            <span className="tpm-saved">{fmtDate(savedAt)}</span>
          </div>
          <button className="tpm-close" onClick={onClose} aria-label="Close">
            <X size={15} strokeWidth={2} />
          </button>
        </div>

        {/* ── Route ── */}
        <div className="tpm-route">
          <div className="tpm-route-row">
            <MapPin size={11} strokeWidth={2} className="tpm-route-icon tpm-icon-origin" />
            <span className="tpm-route-label">From</span>
            <span className="tpm-route-value">{form.current_location}</span>
          </div>
          <div className="tpm-route-connector">
            <div className="tpm-route-line" />
          </div>
          <div className="tpm-route-row">
            <MapPin size={11} strokeWidth={2} className="tpm-route-icon tpm-icon-waypoint" />
            <span className="tpm-route-label">Pickup</span>
            <span className="tpm-route-value">{form.pickup_location}</span>
          </div>
          <div className="tpm-route-connector">
            <div className="tpm-route-line" />
          </div>
          <div className="tpm-route-row">
            <MapPin size={11} strokeWidth={2} className="tpm-route-icon tpm-icon-dest" />
            <span className="tpm-route-label">Dropoff</span>
            <span className="tpm-route-value">{form.dropoff_location}</span>
          </div>
        </div>

        {/* ── Compliance badge ── */}
        <div className="tpm-compliance">
          <StatusIcon size={13} strokeWidth={2.5} style={{ color: statusColor, flexShrink: 0 }} />
          <span className="tpm-compliance-label" style={{ color: statusColor }}>{statusLabel}</span>
          <span className="tpm-cycle-input">
            {form.current_cycle_used_hours}h cycle used at departure
          </span>
        </div>

        {/* ── Stats grid ── */}
        <div className="tpm-stats">
          <div className="tpm-stat">
            <span className="tpm-stat-value">
              {Math.round(summary.total_distance_miles).toLocaleString()} mi
            </span>
            <span className="tpm-stat-label">Total Distance</span>
          </div>
          <div className="tpm-stat">
            <span className="tpm-stat-value">
              {summary.number_of_days} day{summary.number_of_days !== 1 ? "s" : ""}
            </span>
            <span className="tpm-stat-label">On Road</span>
          </div>
          <div className="tpm-stat">
            <span className="tpm-stat-value">{fmtHours(summary.estimated_total_hours)}</span>
            <span className="tpm-stat-label">HOS Sim Time</span>
          </div>
          <div className="tpm-stat">
            <span className="tpm-stat-value">{fmtHours(summary.cycle_hours_remaining)}</span>
            <span className="tpm-stat-label">Cycle Remaining</span>
          </div>
        </div>

        {/* ── Planner actions ── */}
        <PlannerActions markers={markers} />

        {/* ── Actions ── */}
        <div className="tpm-footer">
          <button
            type="button"
            className="tpm-btn-remove"
            onClick={() => { onRemove(trip.id); onClose(); }}
          >
            <Trash2 size={12} />
            Remove
          </button>
          <div className="tpm-footer-right">
            <button type="button" className="tpm-btn-cancel" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="tpm-btn-load"
              onClick={() => { onLoad(trip); onClose(); }}
            >
              Load Trip
              <ArrowRight size={13} />
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
