export function formatHours(h) {
  let hrs  = Math.floor(h);
  let mins = Math.round((h - hrs) * 60);
  // Normalize: if minutes round to 60, roll into the next hour
  if (mins === 60) { hrs += 1; mins = 0; }
  if (mins === 0) return `${hrs}h`;
  return `${hrs}h ${mins}m`;
}

export function formatMiles(m) {
  return `${Math.round(Number(m)).toLocaleString()} mi`;
}

export const STOP_META = {
  pre_trip: {
    label: "Pre-Trip",
    sublabel: "On-duty — vehicle inspection",
    color: "#6366f1", bg: "rgba(99,102,241,.12)",
  },
  pickup:  {
    label: "Pickup",
    sublabel: "On-duty — loading & paperwork",
    color: "#3b82f6", bg: "rgba(59,130,246,.12)",
  },
  dropoff: {
    label: "Dropoff",
    sublabel: "On-duty — unloading & paperwork",
    color: "#10b981", bg: "rgba(16,185,129,.12)",
  },
  rest: {
    label: "Mandatory Break",
    sublabel: "Off-duty — 30 min (8h driving rule)",
    color: "#f59e0b", bg: "rgba(245,158,11,.12)",
  },
  sleeper: {
    label: "Sleeper Berth",
    sublabel: "Off-duty — resets 11h driving & 14h duty window",
    color: "#8b5cf6", bg: "rgba(139,92,246,.12)",
  },
  fuel: {
    label: "Fuel Stop",
    sublabel: "On-duty — refuel (every 1,000 mi)",
    color: "#ef4444", bg: "rgba(239,68,68,.12)",
  },
};

export const STATUS_META = {
  D:   { label: "Driving",              color: "#3b82f6" },
  ON:  { label: "On Duty (Not Driving)", color: "#f59e0b" },
  SB:  { label: "Sleeper Berth",        color: "#8b5cf6" },
  OFF: { label: "Off Duty",             color: "#6b7280" },
};
