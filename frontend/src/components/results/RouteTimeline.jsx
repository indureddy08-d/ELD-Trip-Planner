import {
  ClipboardCheck, Package, Flag, Coffee, BedDouble, Fuel,
} from "lucide-react";
import { formatHours, formatMiles } from "../../utils/formatters";

// ── Stop type base config ─────────────────────────────────────────────────────
//
// Three visual registers:
//   destination  pickup / dropoff — the reason the trip exists
//   rest         sleeper / break  — compliance-driven pauses
//   service      pre_trip / fuel  — brief operational annotations

const STOP_BASE = {
  pre_trip: {
    Icon: ClipboardCheck,
    label: "Pre-Trip Inspection",
    sublabel: "On-duty · vehicle inspection before departure",
    color: "#6366f1",
    register: "service",
  },
  pickup: {
    Icon: Package,
    label: "Pickup",
    sublabel: "On-duty · loading & paperwork",
    color: "#4f8ef7",
    register: "destination",
  },
  dropoff: {
    Icon: Flag,
    label: "Dropoff",
    sublabel: "On-duty · unloading & paperwork",
    color: "#10b981",
    register: "destination",
  },
  rest: {
    Icon: Coffee,
    label: "Mandatory Break",
    sublabel: "Off-duty · 30 min · required after 8h cumulative driving (49 CFR 395.3)",
    color: "#e8960a",
    register: "rest",
  },
  sleeper: {
    Icon: BedDouble,
    label: "Sleeper Berth (10h)",
    sublabel: "Off-duty · full 10h rest · resets 11h driving & 14h on-duty windows",
    color: "#8b5cf6",
    register: "rest",
  },
  fuel: {
    Icon: Fuel,
    label: "Fuel Stop",
    sublabel: "On-duty · required every 1,000 miles",
    color: "#ef4444",
    register: "service",
  },
};

// ── Per-stop config resolver ──────────────────────────────────────────────────
//
// Returns the display config for a stop. All sleeper stops use the same
// 10h label — split sleeper is not used in this planner.

function resolveStopConfig(stop) {
  return STOP_BASE[stop.stop_type] ?? STOP_BASE.rest;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function drivingMilesBetween(stops, idx) {
  if (idx === 0) return null;
  const delta = stops[idx].cumulative_miles - stops[idx - 1].cumulative_miles;
  return delta > 0.5 ? delta : null;
}

// ── Driving segment — the line between stops ──────────────────────────────────

function DrivingSegment({ miles }) {
  return (
    <div className="tl-segment">
      <div className="tl-segment-line" />
      {miles != null && (
        <span className="tl-segment-miles">{formatMiles(miles)}</span>
      )}
    </div>
  );
}

// ── Destination stop — pickup / dropoff ───────────────────────────────────────

function DestinationStop({ stop, cfg }) {
  const { Icon, label, sublabel, color } = cfg;
  const departure = stop.arrival_hour + stop.duration_hours;

  return (
    <div className="tl-destination">
      {/* Time column */}
      <div className="tl-dest-time">
        <span className="tl-dest-hour">{formatHours(stop.arrival_hour)}</span>
        <span className="tl-dest-time-label">arrival</span>
      </div>

      {/* Node */}
      <div className="tl-dest-node" style={{ "--dest-color": color }}>
        <Icon size={14} strokeWidth={2} />
      </div>

      {/* Content */}
      <div className="tl-dest-content">
        {/* Type label leads — color + weight make it the first thing you read */}
        <div className="tl-dest-type" style={{ color }}>{label}</div>
        {/* Location is the headline */}
        <div className="tl-dest-location">{stop.location_name}</div>
        <div className="tl-dest-meta">
          <div className="tl-dest-meta-row">
            <span>{sublabel}</span>
            <span className="tl-dest-meta-sep">·</span>
            <span>{formatHours(stop.duration_hours)}</span>
          </div>
          <div className="tl-dest-meta-row">
            <span className="tl-dest-depart">Depart {formatHours(departure)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Rest event — sleeper / mandatory break ────────────────────────────────────

function RestEvent({ stop, cfg }) {
  const { Icon, label, sublabel, color } = cfg;
  const isSleeper = stop.stop_type === "sleeper";
  const departure = stop.arrival_hour + stop.duration_hours;

  return (
    <div
      className={`tl-rest ${isSleeper ? "tl-rest-sleeper" : "tl-rest-break"}`}
      style={{ "--rest-color": color }}
    >
      <div className="tl-rest-icon">
        <Icon size={isSleeper ? 14 : 12} strokeWidth={2} />
      </div>
      <div className="tl-rest-body">
        <div className="tl-rest-label" style={{ color }}>{label}</div>
        <div className="tl-rest-sublabel">{sublabel}</div>
      </div>
      <div className="tl-rest-times">
        <span className="tl-rest-duration">{formatHours(stop.duration_hours)}</span>
        <span className="tl-rest-window">
          {formatHours(stop.arrival_hour)} → {formatHours(departure)}
        </span>
      </div>
    </div>
  );
}

// ── Service annotation — pre_trip / fuel ──────────────────────────────────────

function ServiceAnnotation({ stop, cfg }) {
  const { Icon, label, sublabel, color } = cfg;
  const departure = stop.arrival_hour + stop.duration_hours;

  return (
    <div className="tl-service">
      <Icon size={11} strokeWidth={2} style={{ color, flexShrink: 0 }} />
      <div className="tl-service-body">
        <div className="tl-service-top">
          <span className="tl-service-label" style={{ color }}>{label}</span>
          <span className="tl-service-location">{stop.location_name}</span>
          <span className="tl-service-times">
            {formatHours(stop.arrival_hour)} · {formatHours(stop.duration_hours)} · → {formatHours(departure)}
          </span>
        </div>
        {sublabel && (
          <div className="tl-service-sublabel">{sublabel}</div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function RouteTimeline({ stops }) {
  if (!stops?.length) {
    return (
      <div className="timeline-empty">
        Plan a trip to see the stop-by-stop timeline here.
      </div>
    );
  }

  return (
    <div className="tl-root">
      {stops.map((stop, idx) => {
        const cfg   = resolveStopConfig(stop);
        const miles = drivingMilesBetween(stops, idx);

        return (
          <div key={idx} className="tl-event">
            {idx > 0 && <DrivingSegment miles={miles} />}

            {cfg.register === "destination" && (
              <DestinationStop stop={stop} cfg={cfg} />
            )}
            {cfg.register === "rest" && (
              <RestEvent stop={stop} cfg={cfg} />
            )}
            {cfg.register === "service" && (
              <ServiceAnnotation stop={stop} cfg={cfg} />
            )}
          </div>
        );
      })}
    </div>
  );
}
