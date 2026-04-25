import { useState, useEffect, useRef, useCallback } from "react";

const MAX_ON_DUTY_HOURS  = 14.0;
const MAX_DRIVING_HOURS  = 11.0;

/**
 * Session-based duty timer.
 * All state is in-memory — refreshing the page resets it.
 * This is intentional: the feature is operational/demo only,
 * not official live telematics.
 */
export function useDutySession(tripResult) {
  const [status, setStatus]       = useState("idle");   // idle | active | ended
  const [startedAt, setStartedAt] = useState(null);     // Date
  const [endedAt, setEndedAt]     = useState(null);     // Date
  const [elapsed, setElapsed]     = useState(0);        // seconds
  const [now, setNow]             = useState(new Date()); // live wall clock
  const tickRef = useRef(null);

  const startDuty = useCallback(() => {
    const t = new Date();
    setStartedAt(t);
    setEndedAt(null);
    setElapsed(0);
    setNow(t);
    setStatus("active");
  }, []);

  const endDuty = useCallback(() => {
    setEndedAt(new Date());
    setStatus("ended");
  }, []);

  // Reset back to idle — clears all session state so a new session can begin
  const resetDuty = useCallback(() => {
    setStartedAt(null);
    setEndedAt(null);
    setElapsed(0);
    setNow(new Date());
    setStatus("idle");
  }, []);

  // Tick every second while active — updates both elapsed and wall clock
  useEffect(() => {
    if (status === "active") {
      tickRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
        setNow(new Date());
      }, 1000);
    } else {
      clearInterval(tickRef.current);
    }
    return () => clearInterval(tickRef.current);
  }, [status]);

  const elapsedHours = elapsed / 3600;
  const remainingOnDuty  = Math.max(0, MAX_ON_DUTY_HOURS  - elapsedHours);
  const remainingDriving = Math.max(0, MAX_DRIVING_HOURS  - elapsedHours);

  // Estimate time to pickup and dropoff from the trip plan
  let timeToPickup  = null;
  let timeToDropoff = null;

  if (tripResult?.stops) {
    const pickup  = tripResult.stops.find((s) => s.stop_type === "pickup");
    const dropoff = tripResult.stops.find((s) => s.stop_type === "dropoff");

    if (pickup) {
      // arrival_hour is hours from trip start (HOS sim time)
      // We show it as "estimated hours remaining" from now
      timeToPickup = Math.max(0, pickup.arrival_hour - elapsedHours);
    }
    if (dropoff) {
      timeToDropoff = Math.max(0, dropoff.arrival_hour - elapsedHours);
    }
  }

  return {
    status,
    startedAt,
    endedAt,
    now,               // live wall clock (updates every second while active)
    elapsed,           // seconds
    elapsedHours,
    remainingOnDuty,
    remainingDriving,
    timeToPickup,
    timeToDropoff,
    startDuty,
    endDuty,
    resetDuty,
  };
}
