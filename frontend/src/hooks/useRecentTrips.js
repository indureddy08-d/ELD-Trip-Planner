import { useState, useCallback } from "react";

const STORAGE_KEY = "eld_recent_trips";
const MAX_ENTRIES = 5;

// ── Persistence helpers ───────────────────────────────────────────────────────

function readStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeStorage(entries) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // localStorage unavailable (private browsing, quota exceeded) — fail silently
  }
}

// ── Compliance status derivation ──────────────────────────────────────────────
// Derive at save time so the stored entry is self-contained.

function deriveComplianceStatus(warnings, summary) {
  if (summary.cycle_hours_remaining === 0) return "illegal";
  if (warnings?.some((w) => w.code === "CYCLE_EXCEEDED")) return "illegal";
  if (warnings?.some((w) => w.code === "CYCLE_LOW")) return "warning";
  return "compliant";
}

// ── Planner markers — what the engine inserted ────────────────────────────────
// Stored as counts so the display is self-contained without re-processing stops.

function deriveMarkers(stops) {
  return {
    breaks:    stops.filter((s) => s.stop_type === "rest").length,
    sleepers:  stops.filter((s) => s.stop_type === "sleeper").length,
    fuelStops: stops.filter((s) => s.stop_type === "fuel").length,
  };
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useRecentTrips() {
  const [trips, setTrips] = useState(() => readStorage());

  // Called after a successful planTrip response
  const saveTrip = useCallback((form, result) => {
    const entry = {
      id: Date.now(),
      savedAt: new Date().toISOString(),
      form: {
        current_location:         form.current_location,
        pickup_location:          form.pickup_location,
        dropoff_location:         form.dropoff_location,
        current_cycle_used_hours: String(form.current_cycle_used_hours),
      },
      summary: {
        total_distance_miles:      result.summary.total_distance_miles,
        number_of_days:            result.summary.number_of_days,
        estimated_total_hours:     result.summary.estimated_total_hours,
        cycle_hours_remaining:     result.summary.cycle_hours_remaining,
      },
      complianceStatus: deriveComplianceStatus(result.warnings, result.summary),
      markers: deriveMarkers(result.stops ?? []),
    };

    setTrips((prev) => {
      // Deduplicate: same origin→pickup→dropoff replaces the previous entry
      const filtered = prev.filter(
        (t) =>
          t.form.current_location !== entry.form.current_location ||
          t.form.pickup_location  !== entry.form.pickup_location  ||
          t.form.dropoff_location !== entry.form.dropoff_location
      );
      const next = [entry, ...filtered].slice(0, MAX_ENTRIES);
      writeStorage(next);
      return next;
    });
  }, []);

  const clearTrips = useCallback(() => {
    writeStorage([]);
    setTrips([]);
  }, []);

  const removeTrip = useCallback((id) => {
    setTrips((prev) => {
      const next = prev.filter((t) => t.id !== id);
      writeStorage(next);
      return next;
    });
  }, []);

  return { trips, saveTrip, clearTrips, removeTrip };
}
