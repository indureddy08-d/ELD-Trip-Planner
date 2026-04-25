"""
Trip Plan Invariant Checks

Lightweight post-planning validation layer. Called after the HOS engine
produces a plan and before the response is returned or persisted.

Design principles:
- Each check is a small, named function — easy to read, easy to extend
- All failures raise AssertionError with a clear message
- In production these surface as HTTP 500 (unexpected engine bug)
- In development / tests they fail loudly and immediately
- No business logic lives here — only structural correctness checks
"""
from __future__ import annotations

from compliance.hos_rules import (
    MANDATORY_BREAK_AFTER, MANDATORY_BREAK_DURATION,
    PICKUP_DURATION, DROPOFF_DURATION, FUEL_INTERVAL_MILES,
)

# Float tolerance for hour/mile comparisons (avoids false positives from rounding)
_HOUR_TOLERANCE = 0.05
_MILE_TOLERANCE = 1.0


def assert_plan_invariants(stops: list[dict], eld_logs: list[dict], summary: dict) -> None:
    """
    Run all structural invariant checks on a completed trip plan.
    Raises AssertionError if any check fails.
    Call this after _build_stop_schedule() and generate_eld_logs() complete.
    """
    _check_stop_durations_positive(stops)
    _check_no_negative_miles(stops)
    _check_stop_sequence(stops)
    _check_pickup_before_dropoff(stops)
    _check_no_overlapping_stops(stops)
    _check_eld_daily_hours(eld_logs)
    _check_eld_timeline_continuity(eld_logs)
    _check_summary_non_negative(summary)


def assert_cross_layer_consistency(
    stops: list[dict],
    eld_logs: list[dict],
    summary: dict,
    route_instructions: list[dict],
) -> None:
    """
    Cross-layer consistency checks — verify that summary, stops, ELD logs,
    and route instructions all tell the same story.

    These catch bugs where one layer is computed from stale or inconsistent
    data, e.g. summary.number_of_days disagrees with len(eld_logs).
    """
    _check_summary_stop_count(stops, summary)
    _check_summary_day_count(eld_logs, summary)
    _check_eld_day_sequence(eld_logs)
    _check_pickup_duration_in_stops(stops)
    _check_dropoff_duration_in_stops(stops)
    _check_eld_contains_pickup_and_dropoff(stops, eld_logs)
    _check_rest_stops_are_off_duty_in_eld(stops, eld_logs)
    _check_fuel_stops_are_on_duty_in_eld(stops, eld_logs)
    _check_instructions_cover_all_stop_types(stops, route_instructions)
    _check_eld_total_miles_plausible(eld_logs, summary)
    _check_fuel_stops_within_interval(stops)


# ── Structural checks ─────────────────────────────────────────────────────────

def _check_stop_durations_positive(stops: list[dict]) -> None:
    """Every stop must have a positive duration — zero or negative is a planner bug."""
    for i, stop in enumerate(stops):
        assert stop["duration_hours"] > 0, (
            f"Stop {i} ({stop['stop_type']} @ {stop['location_name']}) "
            f"has non-positive duration: {stop['duration_hours']}h"
        )


def _check_no_negative_miles(stops: list[dict]) -> None:
    """Cumulative miles must be non-negative and non-decreasing."""
    prev = 0.0
    for i, stop in enumerate(stops):
        miles = stop["cumulative_miles"]
        assert miles >= 0, (
            f"Stop {i} ({stop['stop_type']}) has negative cumulative miles: {miles}"
        )
        assert miles >= prev - _HOUR_TOLERANCE, (
            f"Stop {i} ({stop['stop_type']}) cumulative miles {miles} "
            f"decreased from previous {prev} — stops must be ordered"
        )
        prev = miles


def _check_stop_sequence(stops: list[dict]) -> None:
    """Arrival hours must be non-decreasing."""
    prev_arrival = 0.0
    for i, stop in enumerate(stops):
        assert stop["arrival_hour"] >= prev_arrival - _HOUR_TOLERANCE, (
            f"Stop {i} ({stop['stop_type']} @ {stop['location_name']}) "
            f"arrives at {stop['arrival_hour']}h which is before "
            f"previous stop at {prev_arrival}h"
        )
        prev_arrival = stop["arrival_hour"]


def _check_pickup_before_dropoff(stops: list[dict]) -> None:
    """Pickup must appear before dropoff in the stop list."""
    pickup_hour  = next((s["arrival_hour"] for s in stops if s["stop_type"] == "pickup"),  None)
    dropoff_hour = next((s["arrival_hour"] for s in stops if s["stop_type"] == "dropoff"), None)

    assert pickup_hour is not None,  "Plan has no pickup stop"
    assert dropoff_hour is not None, "Plan has no dropoff stop"
    assert pickup_hour < dropoff_hour, (
        f"Pickup at {pickup_hour}h must occur before dropoff at {dropoff_hour}h"
    )


def _check_no_overlapping_stops(stops: list[dict]) -> None:
    """No two stops may overlap in time."""
    for i in range(len(stops) - 1):
        current_end = stops[i]["arrival_hour"] + stops[i]["duration_hours"]
        next_start  = stops[i + 1]["arrival_hour"]
        assert current_end <= next_start + _HOUR_TOLERANCE, (
            f"Stop {i} ({stops[i]['stop_type']}) ends at {round(current_end, 2)}h "
            f"but stop {i+1} ({stops[i+1]['stop_type']}) starts at {next_start}h — overlap detected"
        )


def _check_eld_daily_hours(eld_logs: list[dict]) -> None:
    """The sum of all duty status hours in a single ELD log must not exceed 24."""
    for log in eld_logs:
        total = (
            log["driving_hours"]
            + log["on_duty_not_driving_hours"]
            + log["sleeper_berth_hours"]
            + log["off_duty_hours"]
        )
        assert total <= 24.0 + _HOUR_TOLERANCE, (
            f"ELD Day {log['day_number']} ({log['log_date']}) total hours "
            f"{round(total, 2)} exceeds 24"
        )
        for field in ("driving_hours", "on_duty_not_driving_hours",
                      "sleeper_berth_hours", "off_duty_hours"):
            assert log[field] >= 0, (
                f"ELD Day {log['day_number']} has negative {field}: {log[field]}"
            )


def _check_summary_non_negative(summary: dict) -> None:
    """Key summary fields must be non-negative."""
    for field in ("total_distance_miles", "deadhead_miles", "loaded_miles",
                  "estimated_total_hours", "cycle_hours_remaining"):
        val = summary.get(field, 0)
        assert val >= 0, (
            f"Summary field '{field}' is negative: {val}"
        )


# ── Cross-layer consistency checks ────────────────────────────────────────────

def _check_summary_stop_count(stops: list[dict], summary: dict) -> None:
    """
    summary.number_of_stops must equal len(stops).
    Catches a bug where the summary is built from stale stop data.
    """
    assert summary["number_of_stops"] == len(stops), (
        f"summary.number_of_stops={summary['number_of_stops']} "
        f"but actual stop count is {len(stops)}"
    )


def _check_summary_day_count(eld_logs: list[dict], summary: dict) -> None:
    """
    summary.number_of_days must equal len(eld_logs).
    Catches a bug where the summary day count disagrees with the ELD output.
    """
    assert summary["number_of_days"] == len(eld_logs), (
        f"summary.number_of_days={summary['number_of_days']} "
        f"but ELD log count is {len(eld_logs)}"
    )


def _check_pickup_duration_in_stops(stops: list[dict]) -> None:
    """
    The pickup stop must have duration == PICKUP_DURATION.
    Catches a regression where pickup time is hardcoded differently from the constant.
    """
    pickup_stops = [s for s in stops if s["stop_type"] == "pickup"]
    assert len(pickup_stops) == 1, f"Expected exactly 1 pickup stop, found {len(pickup_stops)}"
    actual = pickup_stops[0]["duration_hours"]
    assert abs(actual - PICKUP_DURATION) <= _HOUR_TOLERANCE, (
        f"Pickup duration is {actual}h but PICKUP_DURATION constant is {PICKUP_DURATION}h"
    )


def _check_dropoff_duration_in_stops(stops: list[dict]) -> None:
    """
    The dropoff stop must have duration == DROPOFF_DURATION.
    Catches a regression where dropoff time is hardcoded differently from the constant.
    """
    dropoff_stops = [s for s in stops if s["stop_type"] == "dropoff"]
    assert len(dropoff_stops) == 1, f"Expected exactly 1 dropoff stop, found {len(dropoff_stops)}"
    actual = dropoff_stops[0]["duration_hours"]
    assert abs(actual - DROPOFF_DURATION) <= _HOUR_TOLERANCE, (
        f"Dropoff duration is {actual}h but DROPOFF_DURATION constant is {DROPOFF_DURATION}h"
    )


def _check_eld_contains_pickup_and_dropoff(stops: list[dict], eld_logs: list[dict]) -> None:
    """
    The ELD timeline must contain ON-duty segments for pickup and dropoff.
    Catches a bug where the ELD generator maps these to the wrong duty status.
    """
    all_timeline = [seg for log in eld_logs for seg in log["timeline"]]
    on_labels = {seg["label"].lower() for seg in all_timeline if seg["status"] == "ON"}

    assert any("pickup" in label for label in on_labels), (
        "ELD timeline has no ON-duty segment for pickup — "
        "check _STOP_DUTY_MAP in logs/generator.py"
    )
    assert any("dropoff" in label for label in on_labels), (
        "ELD timeline has no ON-duty segment for dropoff — "
        "check _STOP_DUTY_MAP in logs/generator.py"
    )


def _check_rest_stops_are_off_duty_in_eld(stops: list[dict], eld_logs: list[dict]) -> None:
    """
    Every mandatory 30-minute rest stop must appear as OFF_DUTY in the ELD
    timeline — never as ON_DUTY or SB.

    This enforces the FMCSA model: the qualifying break is off-duty and must
    NOT consume the 14-hour on-duty window. If a rest stop is mapped to ON
    in the ELD, the 14h window would be incorrectly shortened.

    Also verifies that the ELD log containing the break has non-zero
    off_duty_hours — a rest stop that silently disappears from the totals
    would be a generator bug.
    """
    rest_stops = [s for s in stops if s["stop_type"] == "rest"]
    if not rest_stops:
        return  # no break required on this trip — nothing to check

    all_timeline = [seg for log in eld_logs for seg in log["timeline"]]

    # Every OFF segment with "break" or "mandatory" in the label is a rest entry
    off_break_segments = [
        seg for seg in all_timeline
        if seg["status"] == "OFF"
        and ("break" in seg["label"].lower() or "mandatory" in seg["label"].lower())
    ]

    assert len(off_break_segments) >= len(rest_stops), (
        f"Found {len(rest_stops)} rest stop(s) in the plan but only "
        f"{len(off_break_segments)} OFF-duty break segment(s) in the ELD timeline. "
        "Check _STOP_DUTY_MAP in logs/generator.py — 'rest' must map to 'OFF'."
    )

    # Confirm no rest stop was accidentally mapped to ON or SB
    on_break_segments = [
        seg for seg in all_timeline
        if seg["status"] in ("ON", "SB")
        and ("break" in seg["label"].lower() or "mandatory" in seg["label"].lower())
    ]
    assert len(on_break_segments) == 0, (
        f"Mandatory break segment(s) found with ON or SB status in ELD timeline: "
        f"{on_break_segments}. The 30-min break must be OFF_DUTY."
    )

    # Each day that contains a rest stop must have positive off_duty_hours
    for rest in rest_stops:
        rest_day_idx = int(rest["arrival_hour"] / 24)
        matching_logs = [
            log for log in eld_logs
            if log["day_number"] == rest_day_idx + 1
        ]
        for log in matching_logs:
            assert log["off_duty_hours"] > 0, (
                f"ELD Day {log['day_number']} contains a rest stop but "
                f"off_duty_hours is 0 — the break is not reflected in daily totals."
            )


def _check_instructions_cover_all_stop_types(
    stops: list[dict], route_instructions: list[dict]
) -> None:
    """
    Every stop type present in the stop list must appear in at least one
    route instruction. Catches a bug where a new stop type is added to the
    planner but forgotten in _build_instructions.
    """
    stop_types_present = {s["stop_type"] for s in stops}
    instruction_text = " ".join(
        (step.get("instruction", "") + " " + step.get("details", "")).lower()
        for step in route_instructions
    )

    # Map stop types to keywords that must appear in instructions
    _KEYWORD_MAP = {
        "pickup":   "pickup",
        "dropoff":  "dropoff",
        "rest":     "break",
        "sleeper":  "sleeper",
        "fuel":     "fuel",
        "pre_trip": "inspection",
    }

    for stop_type in stop_types_present:
        keyword = _KEYWORD_MAP.get(stop_type)
        if keyword:
            assert keyword in instruction_text, (
                f"Stop type '{stop_type}' is in the stop list but the keyword "
                f"'{keyword}' does not appear in any route instruction — "
                f"check _build_instructions in trips/planner.py"
            )


def _check_eld_total_miles_plausible(eld_logs: list[dict], summary: dict) -> None:
    """
    The sum of daily miles across all ELD logs must be within tolerance of
    summary.total_distance_miles. Catches a bug in the ELD mile calculation.
    """
    eld_total = sum(log["total_miles"] for log in eld_logs)
    summary_total = summary["total_distance_miles"]

    # Allow up to 5% variance — ELD miles use AVG_SPEED_MPH * driving_hours
    # which may differ slightly from the routing-derived distance
    tolerance = max(summary_total * 0.05, 10.0)
    assert abs(eld_total - summary_total) <= tolerance, (
        f"ELD total miles ({eld_total}) differs from summary total "
        f"({summary_total}) by more than {round(tolerance)} miles"
    )


def _check_fuel_stops_within_interval(stops: list[dict]) -> None:
    """
    No two consecutive fuel stops should be more than FUEL_INTERVAL_MILES apart.
    Also verifies the first fuel stop is not before the interval threshold.
    Catches a bug where the fuel stop insertion logic fires too early or too late.
    """
    fuel_stops = [s for s in stops if s["stop_type"] == "fuel"]
    if not fuel_stops:
        return  # short trip — no fuel stops expected

    # First fuel stop must be at approximately FUEL_INTERVAL_MILES
    first_fuel_miles = fuel_stops[0]["cumulative_miles"]
    assert first_fuel_miles >= FUEL_INTERVAL_MILES - _MILE_TOLERANCE, (
        f"First fuel stop at mile {first_fuel_miles} is before the "
        f"{FUEL_INTERVAL_MILES}-mile threshold"
    )

    # Consecutive fuel stops must not exceed the interval
    for i in range(len(fuel_stops) - 1):
        gap = fuel_stops[i + 1]["cumulative_miles"] - fuel_stops[i]["cumulative_miles"]
        assert gap <= FUEL_INTERVAL_MILES + _MILE_TOLERANCE, (
            f"Gap between fuel stop {i} and {i+1} is {round(gap)} miles — "
            f"exceeds the {FUEL_INTERVAL_MILES}-mile interval"
        )


def _check_fuel_stops_are_on_duty_in_eld(stops: list[dict], eld_logs: list[dict]) -> None:
    """
    Every fuel stop must appear as ON_DUTY (not driving) in the ELD timeline.

    Fuel stops are on-duty not driving — they count against the 14-hour window
    and the 70-hour cycle. A regression that maps fuel to OFF or SB would
    silently under-count on-duty time, producing an incorrect ELD record.

    Also verifies that the ELD log containing the fuel stop has non-zero
    on_duty_not_driving_hours — a fuel stop that disappears from totals
    would be a generator bug.
    """
    fuel_stops = [s for s in stops if s["stop_type"] == "fuel"]
    if not fuel_stops:
        return  # short trip — nothing to check

    all_timeline = [seg for log in eld_logs for seg in log["timeline"]]

    # Every ON segment with "fuel" in the label is a fuel stop entry
    on_fuel_segments = [
        seg for seg in all_timeline
        if seg["status"] == "ON" and "fuel" in seg["label"].lower()
    ]

    assert len(on_fuel_segments) >= len(fuel_stops), (
        f"Found {len(fuel_stops)} fuel stop(s) in the plan but only "
        f"{len(on_fuel_segments)} ON-duty fuel segment(s) in the ELD timeline. "
        "Check _STOP_DUTY_MAP in logs/generator.py — 'fuel' must map to 'ON'."
    )

    # Confirm no fuel stop was accidentally mapped to OFF or SB
    wrong_fuel_segments = [
        seg for seg in all_timeline
        if seg["status"] in ("OFF", "SB") and "fuel" in seg["label"].lower()
    ]
    assert len(wrong_fuel_segments) == 0, (
        f"Fuel stop segment(s) found with OFF or SB status in ELD timeline: "
        f"{wrong_fuel_segments}. Fuel stops must be ON_DUTY (not driving)."
    )

    # Each day that contains a fuel stop must have positive on_duty_not_driving_hours
    for fuel in fuel_stops:
        fuel_day_idx = int(fuel["arrival_hour"] / 24)
        matching_logs = [
            log for log in eld_logs
            if log["day_number"] == fuel_day_idx + 1
        ]
        for log in matching_logs:
            assert log["on_duty_not_driving_hours"] > 0, (
                f"ELD Day {log['day_number']} contains a fuel stop but "
                f"on_duty_not_driving_hours is 0 — the stop is not reflected in daily totals."
            )


def _check_eld_timeline_continuity(eld_logs: list[dict]) -> None:
    """
    For every ELD log day, the timeline segments must:
      1. Start at 0.0h (beginning of the 24-hour window)
      2. End at 24.0h for all non-final days (full day accounted for)
      3. Have no gaps between consecutive segments

    This catches bugs in the generator's gap-filling and tail logic that
    would produce a timeline with holes — visually broken on the frontend
    and structurally invalid for an FMCSA logbook.
    """
    if not eld_logs:
        return

    for log in eld_logs:
        timeline = sorted(log.get("timeline", []), key=lambda s: s["start"])
        if not timeline:
            continue

        day = log["day_number"]
        is_final = (day == eld_logs[-1]["day_number"])

        # First segment must start at 0
        assert abs(timeline[0]["start"]) <= _HOUR_TOLERANCE, (
            f"ELD Day {day}: first timeline segment starts at "
            f"{timeline[0]['start']:.3f}h, expected 0.0h"
        )

        # Non-final days must end at exactly 24h
        if not is_final:
            assert abs(timeline[-1]["end"] - 24.0) <= _HOUR_TOLERANCE, (
                f"ELD Day {day} (non-final): last timeline segment ends at "
                f"{timeline[-1]['end']:.3f}h, expected 24.0h"
            )

        # No gaps between consecutive segments
        for i in range(len(timeline) - 1):
            gap = timeline[i + 1]["start"] - timeline[i]["end"]
            assert abs(gap) <= _HOUR_TOLERANCE, (
                f"ELD Day {day}: gap of {gap:.3f}h between segment {i} "
                f"({timeline[i]['status']} {timeline[i]['start']:.2f}→{timeline[i]['end']:.2f}) "
                f"and segment {i+1} "
                f"({timeline[i+1]['status']} {timeline[i+1]['start']:.2f}→{timeline[i+1]['end']:.2f})"
            )


def _check_eld_day_sequence(eld_logs: list[dict]) -> None:
    """
    ELD log days must be sequentially numbered starting at 1, and each
    log_date must be exactly one calendar day after the previous.

    Catches bugs where the generator skips a day index, produces duplicate
    day numbers, or assigns the wrong calendar date to a log sheet.
    """
    if not eld_logs:
        return

    from datetime import date as _date

    for i, log in enumerate(eld_logs):
        expected_day_number = i + 1
        assert log["day_number"] == expected_day_number, (
            f"ELD log at index {i} has day_number={log['day_number']}, "
            f"expected {expected_day_number} — day numbers must be sequential from 1"
        )

    # Dates must be sequential (each one day after the previous)
    for i in range(len(eld_logs) - 1):
        current_date = _date.fromisoformat(eld_logs[i]["log_date"])
        next_date    = _date.fromisoformat(eld_logs[i + 1]["log_date"])
        delta = (next_date - current_date).days
        assert delta == 1, (
            f"ELD log dates are not sequential: "
            f"Day {eld_logs[i]['day_number']} is {eld_logs[i]['log_date']} "
            f"but Day {eld_logs[i+1]['day_number']} is {eld_logs[i+1]['log_date']} "
            f"({delta} day(s) apart, expected 1)"
        )

