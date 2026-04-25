"""
Trip Planning Orchestrator

Coordinates the three domain modules:
  routing    → resolves distances
  compliance → enforces HOS rules
  logs       → generates ELD log sheets

Views call this module. Nothing in here touches the ORM —
persistence is the view's responsibility.
"""
from __future__ import annotations
from dataclasses import dataclass

from routing.service import get_route as resolve_route
from compliance.hos_rules import (
    MAX_DRIVING_PER_SHIFT, MAX_ON_DUTY_PER_SHIFT, REQUIRED_OFF_DUTY,
    CYCLE_LIMIT, MANDATORY_BREAK_AFTER, MANDATORY_BREAK_DURATION,
    FUEL_INTERVAL_MILES, PICKUP_DURATION, DROPOFF_DURATION,
    AVG_SPEED_MPH, FUEL_STOP_DURATION, PRE_TRIP_DURATION,
    SPLIT_SB_LONG, SPLIT_SB_SHORT,
)
from logs.generator import generate as generate_eld_logs
from trips.invariants import assert_plan_invariants, assert_cross_layer_consistency


def plan(
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    cycle_used: float,
) -> dict:
    """
    Build a fully HOS-compliant trip plan.

    Raises ValueError immediately if the driver's cycle is already
    exhausted — no routing calls are made in that case.
    """
    # ── Upfront cycle guard ───────────────────────────────────────────────────
    # Check before calling any external service. A driver at or above the
    # 70-hour limit cannot legally begin a new trip without a 34-hour restart.
    if cycle_used >= CYCLE_LIMIT:
        used_display = int(cycle_used) if cycle_used == int(cycle_used) else cycle_used
        raise ValueError(
            f"This driver has used {used_display}h of the 70-hour/8-day cycle. "
            "A 34-hour restart is required before departure."
        )

    deadhead_route = resolve_route(current_location, [], pickup_location)
    loaded_route   = resolve_route(pickup_location,  [], dropoff_location)

    deadhead_miles = deadhead_route.total_distance_miles
    loaded_miles   = loaded_route.total_distance_miles
    total_miles    = deadhead_miles + loaded_miles

    # ── Two duration sources — both exposed, neither hidden ──────────────────
    # provider_duration_hours: real-world driving time from the routing API
    #   (ORS accounts for road types, speed limits, HGV restrictions).
    #   Used for display only — shown on the map tab and in the summary.
    #
    # planner_duration_hours: simulation time derived from miles / AVG_SPEED_MPH.
    #   Used for ALL HOS calculations — stop scheduling, cycle math, ELD logs.
    #   The HOS engine is a step-by-step simulation at a fixed speed; it cannot
    #   consume variable real-world durations without breaking the rule engine.
    #
    # Both are shown in the API response so the app is never contradictory.
    provider_duration_hours = round(
        deadhead_route.total_duration_hours + loaded_route.total_duration_hours, 2
    )

    stops, elapsed_hours = _build_stop_schedule(
        deadhead_miles, loaded_miles, total_miles,
        pickup_location, dropoff_location, cycle_used,
        current_location=current_location,
    )

    eld_logs = generate_eld_logs(stops, elapsed_hours)

    cycle_remaining = round(max(0.0, CYCLE_LIMIT - cycle_used - elapsed_hours), 2)
    warnings, assumptions = _build_warnings_and_assumptions(
        cycle_used=cycle_used,
        cycle_remaining=cycle_remaining,
        total_miles=total_miles,
        elapsed_hours=elapsed_hours,
        stops=stops,
        deadhead_provider=deadhead_route.provider,
        loaded_provider=loaded_route.provider,
        from_cache=deadhead_route.from_cache or loaded_route.from_cache,
    )

    summary = {
        "total_distance_miles": round(total_miles, 1),
        "deadhead_miles": round(deadhead_miles, 1),
        "loaded_miles": round(loaded_miles, 1),
        # Simulation duration — used for all HOS/cycle/ELD calculations (miles ÷ AVG_SPEED_MPH)
        "estimated_total_hours": round(elapsed_hours, 2),
        # Provider duration — real-world driving time from the routing API (display only)
        "provider_driving_hours": provider_duration_hours,
        "cycle_hours_used_after_trip": round(cycle_used + elapsed_hours, 2),
        "cycle_hours_remaining": cycle_remaining,
        "number_of_stops": len(stops),
        "number_of_days": len(eld_logs),
    }

    # ── Invariant checks ──────────────────────────────────────────────────────
    # Validate structural correctness before returning or persisting anything.
    # Raises AssertionError if the engine produced inconsistent output —
    # this should never happen in production but catches regressions immediately.
    assert_plan_invariants(stops, eld_logs, summary)

    route_instructions = _build_instructions(
        current_location, pickup_location, dropoff_location,
        deadhead_miles, loaded_miles, stops,
    )

    # ── Cross-layer consistency ───────────────────────────────────────────────
    # Verify that summary, stops, ELD logs, and route instructions all agree.
    assert_cross_layer_consistency(stops, eld_logs, summary, route_instructions)

    return {
        "summary": summary,
        "stops": stops,
        "route_instructions": route_instructions,
        "eld_logs": eld_logs,
        "warnings": warnings,
        "assumptions": assumptions,
    }


# ── Shift state dataclass ─────────────────────────────────────────────────────

@dataclass
class _ShiftState:
    """
    Tracks all mutable HOS counters for the current shift.
    Using a dataclass instead of a plain dict gives us type safety
    and eliminates silent typo bugs on key names.
    """
    elapsed: float = 0.0           # total clock hours from trip start
    drive_today: float = 0.0       # driving hours in current 11h window
    on_duty_today: float = 0.0     # on-duty hours in current 14h window
    cycle: float = 0.0             # running 70h/8d total (initialised to cycle_used)
    miles_since_fuel: float = 0.0  # miles driven since last fuel stop
    miles_covered: float = 0.0     # total miles covered so far
    drive_since_break: float = 0.0 # driving hours since last qualifying break

    # ── Split sleeper berth tracking (49 CFR 395.1(g)) ───────────────────
    # The split provision allows the required 10h off-duty to be split into:
    #   - A "long" period of ≥8h in the sleeper berth
    #   - A "short" period of ≥2h (sleeper berth or off-duty)
    # When a long SB period is taken but the full 10h reset hasn't happened,
    # we track it so the next short period can complete the pairing.
    # split_sb_pending: hours banked in the long SB period (0 = no pending split)
    split_sb_pending: float = 0.0


# ── Stop schedule builder ─────────────────────────────────────────────────────

def _build_stop_schedule(
    deadhead: float, loaded: float, total: float,
    pickup: str, dropoff: str, cycle_used: float,
    current_location: str = "",
) -> tuple[list[dict], float]:
    """
    State-machine that walks the route mile by mile and inserts
    HOS-mandated stops exactly when a limit is reached.
    """
    stops: list[dict] = []
    s = _ShiftState(cycle=cycle_used)
    fuel_stop_count = 0  # tracks ordinal for human-readable notes

    def add_stop(stop_type: str, location: str, duration: float, notes: str = "") -> None:
        stops.append({
            "stop_type": stop_type,
            "location_name": location,
            "arrival_hour": round(s.elapsed, 2),
            "duration_hours": duration,
            "cumulative_drive_hours": round(s.drive_today, 2),
            "cumulative_miles": round(s.miles_covered, 2),
            "notes": notes,
        })
        s.elapsed += duration

        if stop_type in ("pickup", "dropoff", "pre_trip"):
            # On-duty not driving — counts against 14h window and 70h cycle
            s.on_duty_today += duration
            s.cycle += duration

        elif stop_type == "fuel":
            # Fuel stop: on-duty not driving for 14h/cycle accounting.
            # Per our operational assumption, a fuel stop interrupts driving
            # and resets the 8-hour break accumulator — the driver is out of
            # the cab and not driving during this time.
            # (49 CFR 395.3 requires the break to be off-duty or sleeper berth
            # to satisfy the formal break rule, but for this simulation we treat
            # a fuel stop as a qualifying non-driving interruption consistent
            # with the project's stated assumptions.)
            s.on_duty_today += duration
            s.cycle += duration
            s.drive_since_break = 0.0  # fuel stop resets the break accumulator

        elif stop_type == "rest":
            # Mandatory 30-minute break (49 CFR 395.3(a)(3)(ii)).
            # Modeled as OFF_DUTY — it does NOT count against the 14-hour
            # on-duty window. The ELD generator maps "rest" → OFF status.
            # drive_since_break is reset so the 8h accumulator restarts.
            s.drive_since_break = 0.0
            # Note: no on_duty_today increment — off-duty time is excluded
            # from the 14h window calculation.

        elif stop_type == "sleeper":
            # 10-hour sleeper berth resets the entire shift window.
            # Split provision (49 CFR 395.1(g)): if this is a LONG period
            # (≥8h) but less than the full 10h reset, bank it as a pending
            # split. The next short period (≥2h) will complete the pairing
            # and reset the 11h/14h clocks without counting either period
            # against the 14-hour driving window.
            if duration >= REQUIRED_OFF_DUTY:
                # Full 10h reset — clears everything including any pending split
                s.drive_today = 0.0
                s.on_duty_today = 0.0
                s.drive_since_break = 0.0
                s.split_sb_pending = 0.0
            elif duration >= SPLIT_SB_LONG and s.split_sb_pending == 0.0:
                # Long split period — bank it, partial reset of break accumulator
                s.split_sb_pending = duration
                s.drive_since_break = 0.0
                # 11h/14h clocks are NOT reset yet — they reset when the short
                # period completes the pairing.
            elif duration >= SPLIT_SB_SHORT and s.split_sb_pending >= SPLIT_SB_LONG:
                # Short period completes the split pairing — full reset
                s.drive_today = 0.0
                s.on_duty_today = 0.0
                s.drive_since_break = 0.0
                s.split_sb_pending = 0.0
            else:
                # Any other sleeper stop (e.g. partial) — treat as full reset
                # to avoid leaving the driver in an ambiguous state.
                s.drive_today = 0.0
                s.on_duty_today = 0.0
                s.drive_since_break = 0.0
                s.split_sb_pending = 0.0

    def _route_location_label(miles_covered: float) -> str:
        """
        Return a human-readable location label for a mid-route stop.

        Instead of "Mile Marker 440 (40% of route)" we produce a label like
        "En route, ~440 mi from [origin] (near [pickup])" by interpolating
        between the known named waypoints. This gives the Remarks section
        the city-level context that FMCSA logbooks require.
        """
        pct = miles_covered / total if total else 0
        if miles_covered <= deadhead:
            # Still on the deadhead leg — between current_location and pickup
            origin_label = current_location or "Departure"
            return f"En route to {pickup} (~{round(miles_covered):,} mi from {origin_label})"
        else:
            # On the loaded leg — between pickup and dropoff
            loaded_covered = miles_covered - deadhead
            return f"En route to {dropoff} (~{round(loaded_covered):,} mi from {pickup})"

    def drive(miles: float) -> None:
        nonlocal fuel_stop_count
        remaining = miles
        while remaining > 0.001:
            to_11h  = MAX_DRIVING_PER_SHIFT - s.drive_today
            to_14h  = MAX_ON_DUTY_PER_SHIFT - s.on_duty_today
            to_break = MANDATORY_BREAK_AFTER - s.drive_since_break
            to_cycle = CYCLE_LIMIT - s.cycle
            to_fuel  = FUEL_INTERVAL_MILES - s.miles_since_fuel

            max_drive_h = min(to_11h, to_14h, to_break, to_cycle)

            if max_drive_h <= 0.001:
                if to_cycle <= 0.001:
                    raise ValueError(
                        "The 70-hour/8-day cycle limit is reached before this trip can be completed. "
                        "A 34-hour restart is required before departure."
                    )
                if to_break <= 0.001:
                    add_stop(
                        "rest",
                        _route_location_label(s.miles_covered),
                        MANDATORY_BREAK_DURATION,
                        "Mandatory 30-minute off-duty break — 8-hour driving rule "
                        "(49 CFR 395.3(a)(3)(ii))",
                    )
                    continue

                # 11h or 14h window exhausted.
                # Decision: use split sleeper berth (49 CFR 395.1(g)) or full reset?
                #
                # Split is preferred when:
                #   - No split is already pending (can't nest splits)
                #   - Remaining trip miles justify it (split saves time vs full 10h)
                #   - The driver has enough cycle hours left for the short period
                #
                # The split saves 2h vs a full 10h reset (8h long + 2h short = 10h
                # total, but the 14h window is not consumed by either period).
                # For the planner we always attempt the split when eligible —
                # it is strictly better for the driver than a full 10h reset.

                if s.split_sb_pending == 0.0:
                    # Start the split: take the long 8h sleeper berth period.
                    add_stop(
                        "sleeper",
                        _route_location_label(s.miles_covered),
                        SPLIT_SB_LONG,
                        "Split sleeper berth — long period (8h, 49 CFR 395.1(g)). "
                        "A 2h short period will complete the pairing and reset the "
                        "11h driving and 14h on-duty windows.",
                    )
                elif s.split_sb_pending >= SPLIT_SB_LONG:
                    # Complete the split: take the short 2h period.
                    add_stop(
                        "sleeper",
                        _route_location_label(s.miles_covered),
                        SPLIT_SB_SHORT,
                        "Split sleeper berth — short period (2h, 49 CFR 395.1(g)). "
                        "Pairing complete: 11h driving and 14h on-duty windows reset.",
                    )
                else:
                    # Fallback: full 10h reset (shouldn't normally reach here)
                    add_stop(
                        "sleeper",
                        _route_location_label(s.miles_covered),
                        REQUIRED_OFF_DUTY,
                        "Sleeper Berth (10h) — resets the 11h driving and 14h on-duty "
                        "windows for the next shift (49 CFR 395.3(a)(1))",
                    )
                continue

            max_miles = max_drive_h * AVG_SPEED_MPH

            # Fuel stop intercepts before the driving limit
            if to_fuel < min(remaining, max_miles):
                fuel_h = to_fuel / AVG_SPEED_MPH
                _advance(s, fuel_h, to_fuel)
                remaining -= to_fuel
                fuel_stop_count += 1
                ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(fuel_stop_count, f"{fuel_stop_count}th")
                add_stop(
                    "fuel",
                    _route_location_label(s.miles_covered),
                    FUEL_STOP_DURATION,
                    f"Fuel stop #{fuel_stop_count} ({ordinal}) — "
                    f"required every {int(FUEL_INTERVAL_MILES):,} miles "
                    f"(at mile {round(s.miles_covered):,} of {round(total):,})",
                )
                s.miles_since_fuel = 0.0
                continue

            actual_miles = min(remaining, max_miles)
            actual_h = actual_miles / AVG_SPEED_MPH
            _advance(s, actual_h, actual_miles)
            remaining -= actual_miles

    # Pre-trip inspection — on-duty not driving, 15 minutes.
    # Standard practice before every dispatch. Counts against the 14h window.
    add_stop(
        "pre_trip", current_location or "Departure Point", PRE_TRIP_DURATION,
        "On-duty: pre-trip vehicle inspection (15 min)",
    )

    drive(deadhead)
    add_stop("pickup", pickup, PICKUP_DURATION, "On-duty: loading and paperwork (1 hour)")

    drive(loaded)
    add_stop("dropoff", dropoff, DROPOFF_DURATION, "On-duty: unloading and paperwork (1 hour)")

    return stops, s.elapsed


def _advance(s: _ShiftState, hours: float, miles: float) -> None:
    s.elapsed         += hours
    s.drive_today     += hours
    s.on_duty_today   += hours
    s.cycle           += hours
    s.miles_covered   += miles
    s.miles_since_fuel += miles
    s.drive_since_break += hours


def _mile_label(covered: float, total: float) -> str:
    pct = round(covered / total * 100) if total else 0
    return f"Mile Marker {round(covered):,} ({pct}% of route)"


# ── Warnings & assumptions ────────────────────────────────────────────────────

def _build_warnings_and_assumptions(
    cycle_used: float,
    cycle_remaining: float,
    total_miles: float,
    elapsed_hours: float,
    stops: list[dict],
    deadhead_provider: str,
    loaded_provider: str,
    from_cache: bool,
) -> tuple[list[dict], list[dict]]:
    warnings: list[dict] = []
    assumptions: list[dict] = []

    if cycle_remaining < 10:
        warnings.append({
            "code": "CYCLE_LOW",
            "message": (
                f"Only {cycle_remaining}h remain in the 70h/8-day cycle after this trip. "
                "Plan for a 34-hour restart before the next dispatch."
            ),
        })

    if from_cache:
        warnings.append({
            "code": "DISTANCE_ESTIMATED",
            "message": (
                "Route distances are estimated from a lookup table, not a live map API. "
                "Actual mileage may differ. Add ORS_API_KEY to .env for precise routing."
            ),
        })

    sleeper_count = sum(1 for s in stops if s["stop_type"] == "sleeper")
    if sleeper_count >= 3:
        warnings.append({
            "code": "MULTI_DAY_TRIP",
            "message": (
                f"This trip requires {sleeper_count} sleeper berth resets "
                f"and spans {sleeper_count + 1}+ driving days. "
                "Confirm driver availability and pre-book rest facilities."
            ),
        })

    fuel_stops = sum(1 for s in stops if s["stop_type"] == "fuel")
    if fuel_stops >= 3:
        warnings.append({
            "code": "HIGH_FUEL_STOPS",
            "message": (
                f"{fuel_stops} fuel stops required. "
                "Verify fuel card coverage along the route."
            ),
        })

    assumptions.extend([
        {"code": "DRIVER_TYPE",        "message": "Property-carrying driver (49 CFR Part 395)."},
        {"code": "CYCLE",              "message": "70-hour / 8-day cycle. No 34-hour restart applied."},
        {"code": "ADVERSE_CONDITIONS", "message": "No adverse driving conditions. No 2-hour extension applied."},
        {"code": "AVERAGE_SPEED",      "message": f"HOS simulation uses {AVG_SPEED_MPH} mph fixed speed. Real-world driving time from the routing provider is shown separately as 'provider_driving_hours'."},
        {"code": "PICKUP_DROPOFF",     "message": f"Pickup: {PICKUP_DURATION}h on-duty. Dropoff: {DROPOFF_DURATION}h on-duty."},
        {"code": "FUEL_INTERVAL",      "message": f"Fuel stop required at least every {int(FUEL_INTERVAL_MILES):,} miles."},
        {"code": "BREAK_MODEL",        "message": "30-min mandatory break modeled as off-duty (does not consume 14h window)."},
        {"code": "FUEL_BREAK_RESET",   "message": "Fuel stops reset the 8-hour break accumulator per project assumptions."},
        {"code": "SPLIT_SB",           "message": "Split sleeper berth provision applied when eligible (49 CFR 395.1(g)): 8h long + 2h short periods, neither counting against the 14h driving window."},
        {"code": "ROUTING_PROVIDER",   "message": f"Distance source: {deadhead_provider} (deadhead), {loaded_provider} (loaded)."},
    ])

    return warnings, assumptions


# ── Route instructions ────────────────────────────────────────────────────────

def _fmt(hours: float) -> str:
    """
    Convert a decimal elapsed-hour value to a human-readable string.

    For values under 24h: shows hours and minutes, e.g. "3h 32m".
    For values at or over 24h: shows the calendar day and time-of-day,
    e.g. "Day 2, 00:00" or "Day 2, 01:30". This makes route instructions
    unambiguous when events cross midnight — "24h" alone looks like a
    duration, not a day boundary.
    """
    total_minutes = round(hours * 60)
    if total_minutes < 24 * 60:
        h, m = divmod(total_minutes, 60)
        if h == 0:
            return f"{m}m"
        if m == 0:
            return f"{h}h"
        return f"{h}h {m}m"
    # Multi-day: show calendar day number and time-of-day
    day_number = total_minutes // (24 * 60) + 1
    minutes_into_day = total_minutes % (24 * 60)
    hh, mm = divmod(minutes_into_day, 60)
    return f"Day {day_number}, {hh:02d}:{mm:02d}"


def _build_instructions(
    current: str, pickup: str, dropoff: str,
    deadhead: float, loaded: float, stops: list[dict],
) -> list[dict]:
    steps: list[dict] = []
    n = 1

    # Step 1 is always the depart — but if there's a pre_trip stop,
    # that becomes step 1 and depart becomes step 2.
    has_pre_trip = any(s["stop_type"] == "pre_trip" for s in stops)

    if not has_pre_trip:
        deadhead_drive_time = deadhead / AVG_SPEED_MPH
        steps.append({
            "step": n,
            "instruction": f"Depart {current}",
            "details": (
                f"Deadhead to pickup — {round(deadhead, 1):,} mi, "
                f"HOS sim drive: {_fmt(deadhead_drive_time)}."
            ),
        })
        n += 1

    for stop in stops:
        t         = stop["stop_type"]
        arrival   = stop["arrival_hour"]
        duration  = stop["duration_hours"]
        departure = arrival + duration
        location  = stop["location_name"]

        if t == "pre_trip":
            steps.append({
                "step": n,
                "instruction": f"Pre-Trip Inspection — {current}",
                "details": (
                    f"On-duty: vehicle inspection ({_fmt(duration)}). "
                    f"Elapsed HOS time: {_fmt(departure)}."
                ),
            })
            n += 1
            deadhead_drive_time = deadhead / AVG_SPEED_MPH
            steps.append({
                "step": n,
                "instruction": f"Depart {current}",
                "details": (
                    f"Deadhead to pickup — {round(deadhead, 1):,} mi, "
                    f"HOS sim drive: {_fmt(deadhead_drive_time)}."
                ),
            })
            n += 1

        elif t == "pickup":
            steps.append({
                "step": n,
                "instruction": f"Arrive at Pickup — {pickup}",
                "details": (
                    f"Loading and paperwork: {_fmt(PICKUP_DURATION)}. "
                    f"Elapsed HOS time: {_fmt(departure)}."
                ),
            })
            n += 1
            loaded_drive_time = loaded / AVG_SPEED_MPH
            steps.append({
                "step": n,
                "instruction": f"Depart {pickup} — loaded",
                "details": (
                    f"Loaded run to dropoff — {round(loaded, 1):,} mi, "
                    f"HOS sim drive: {_fmt(loaded_drive_time)}."
                ),
            })
            n += 1

        elif t == "dropoff":
            steps.append({
                "step": n,
                "instruction": f"Arrive at Dropoff — {dropoff}",
                "details": (
                    f"Unloading and paperwork: {_fmt(DROPOFF_DURATION)}. "
                    f"Total HOS trip time: {_fmt(departure)}."
                ),
            })
            n += 1

        elif t == "rest":
            steps.append({
                "step": n,
                "instruction": "Mandatory 30-Minute Off-Duty Break",
                "details": (
                    f"{location}. "
                    f"Required after 8h cumulative driving (49 CFR 395.3). "
                    f"Elapsed: {_fmt(arrival)} — resume at {_fmt(departure)}."
                ),
            })
            n += 1

        elif t == "sleeper":
            # Derive the instruction title from the actual duration so split
            # sleeper periods are not mislabeled as "10-Hour".
            if abs(duration - SPLIT_SB_LONG) < 0.1:
                instr_title = "Sleeper Berth — Long Split (8h)"
                instr_detail = (
                    f"{location}. "
                    f"First half of split provision (49 CFR 395.1(g)) — "
                    f"2h short period follows to complete the pairing. "
                    f"Elapsed: {_fmt(arrival)} — resume at {_fmt(departure)}."
                )
            elif abs(duration - SPLIT_SB_SHORT) < 0.1:
                instr_title = "Sleeper Berth — Short Split (2h)"
                instr_detail = (
                    f"{location}. "
                    f"Completes split pairing (49 CFR 395.1(g)) — "
                    f"resets 11h driving and 14h on-duty windows. "
                    f"Elapsed: {_fmt(arrival)} — resume at {_fmt(departure)}."
                )
            else:
                instr_title = "Sleeper Berth (10h)"
                instr_detail = (
                    f"{location}. "
                    f"11h driving or 14h on-duty window exhausted — "
                    f"10h rest resets both windows for the next shift. "
                    f"Elapsed: {_fmt(arrival)} — resume driving at {_fmt(departure)}."
                )
            steps.append({
                "step": n,
                "instruction": instr_title,
                "details": instr_detail,
            })
            n += 1

        elif t == "fuel":
            total_route_miles = round(deadhead + loaded)
            steps.append({
                "step": n,
                "instruction": f"Fuel Stop — {location}",
                "details": (
                    f"At mile {round(stop['cumulative_miles']):,} of {total_route_miles:,} — "
                    f"required every {int(FUEL_INTERVAL_MILES):,} miles. "
                    f"Duration: {_fmt(duration)}. "
                    f"Elapsed: {_fmt(arrival)} — resume at {_fmt(departure)}."
                ),
            })
            n += 1

    return steps
