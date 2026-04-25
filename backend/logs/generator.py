"""
ELD Log Generator

Takes the ordered list of trip stops produced by the HOS planner
and builds one ELD log sheet per calendar day.

This module has zero Django dependencies — it's pure Python so it
can be unit-tested without standing up the ORM.
"""
from __future__ import annotations
from datetime import date, timedelta
from compliance.hos_rules import AVG_SPEED_MPH


def generate(stops: list[dict], total_hours: float, start_date: date | None = None) -> list[dict]:
    """
    Build ELD daily log sheets from a stop timeline.

    Args:
        stops:       Ordered list of stop dicts from the HOS planner.
        total_hours: Total elapsed trip hours (used to size the day loop).
        start_date:  Calendar date for Day 1. Defaults to today.

    Returns:
        List of log dicts, one per active calendar day.
    """
    if not stops:
        return []

    origin_date = start_date or date.today()
    num_days = int(total_hours / 24) + 1
    logs: list[dict] = []

    for day_idx in range(num_days):
        day_start = day_idx * 24.0
        day_end = day_start + 24.0

        driving_h = 0.0
        on_duty_nd_h = 0.0
        sleeper_h = 0.0
        off_duty_h = 0.0
        day_miles = 0.0
        timeline: list[dict] = []
        remarks: list[str] = []

        # prev_hour tracks where we are within this day's window.
        # Reset to day_start each iteration — do NOT carry over from the
        # previous day, as a stop ending after midnight is handled by the
        # clip logic (max/min) below.
        prev_hour = day_start

        for stop in stops:
            s_start = stop["arrival_hour"]
            s_end = s_start + stop["duration_hours"]

            # Skip stops entirely outside this day
            if s_end <= day_start or s_start >= day_end:
                continue

            # Driving gap before this stop
            gap_start = max(prev_hour, day_start)
            gap_end = min(s_start, day_end)
            if gap_end > gap_start:
                gap_h = gap_end - gap_start
                driving_h += gap_h
                day_miles += gap_h * AVG_SPEED_MPH
                timeline.append(_segment("D", "Driving", gap_start - day_start, gap_end - day_start))

            # The stop itself (clipped to this day)
            seg_start = max(s_start, day_start)
            seg_end = min(s_end, day_end)
            seg_h = seg_end - seg_start

            status, label = _stop_duty_status(stop["stop_type"])

            if status == "SB":
                sleeper_h += seg_h
            elif status == "ON":
                on_duty_nd_h += seg_h
            else:
                off_duty_h += seg_h

            timeline.append(_segment(status, label, seg_start - day_start, seg_end - day_start))

            # Generate a logbook-style remark for this stop on the day it starts.
            # Format: "Location — Duty Status (context)"
            # Only on the start day — avoids duplicates for midnight-spanning stops.
            if s_start >= day_start:
                remark = _build_remark(stop)
                if remark:
                    remarks.append(remark)

            prev_hour = s_end

        # Tail of the day — after the last stop
        tail_start = max(prev_hour, day_start)
        if tail_start < day_end:
            tail_h = day_end - tail_start
            last_stop_end = stops[-1]["arrival_hour"] + stops[-1]["duration_hours"]

            if tail_start >= last_stop_end:
                off_duty_h += tail_h
                timeline.append(_segment("OFF", "Off Duty", tail_start - day_start, day_end - day_start))
            else:
                driving_h += tail_h
                day_miles += tail_h * AVG_SPEED_MPH
                timeline.append(_segment("D", "Driving", tail_start - day_start, day_end - day_start))

        # Only emit days with actual on-duty or driving activity
        if driving_h + on_duty_nd_h + sleeper_h > 0:
            logs.append({
                "day_number": day_idx + 1,
                "log_date": str(origin_date + timedelta(days=day_idx)),
                "driving_hours": round(driving_h, 2),
                "on_duty_not_driving_hours": round(on_duty_nd_h, 2),
                "sleeper_berth_hours": round(sleeper_h, 2),
                "off_duty_hours": round(off_duty_h, 2),
                "total_miles": round(day_miles, 1),
                "timeline": timeline,
                "remarks": "; ".join(remarks) if remarks else "",
            })

    return logs


# ── Helpers ───────────────────────────────────────────────────────────────────

_STOP_DUTY_MAP: dict[str, tuple[str, str]] = {
    "pre_trip": ("ON",  "On Duty — Pre-Trip Inspection"),
    "pickup":  ("ON",  "On Duty — Pickup"),
    "dropoff": ("ON",  "On Duty — Dropoff"),
    "fuel":    ("ON",  "On Duty — Fuel Stop"),
    # "rest" is modeled as OFF_DUTY — it satisfies the FMCSA 30-min break
    # requirement and must NOT consume the 14-hour on-duty window.
    "rest":    ("OFF", "Off Duty — Mandatory Break"),
    # Both full (10h) and split (8h long / 2h short) sleeper periods map to SB.
    "sleeper": ("SB",  "Sleeper Berth"),
}


def _stop_duty_status(stop_type: str) -> tuple[str, str]:
    return _STOP_DUTY_MAP.get(stop_type, ("OFF", "Off Duty"))


def _build_remark(stop: dict) -> str:
    """
    Build a logbook-style remark for a stop.

    Format: "Location — Status: Description"

    For split sleeper berth stops, the remark distinguishes the long (8h)
    and short (2h) periods so the log is unambiguous.
    """
    location = stop.get("location_name", "")
    stop_type = stop.get("stop_type", "")
    duration = stop.get("duration_hours", 0)

    def _sleeper_remark(loc: str) -> str:
        from compliance.hos_rules import SPLIT_SB_LONG, SPLIT_SB_SHORT, REQUIRED_OFF_DUTY
        if abs(duration - SPLIT_SB_LONG) < 0.01:
            return f"{loc} — Sleeper Berth: Split provision long period (8h, 49 CFR 395.1(g))"
        elif abs(duration - SPLIT_SB_SHORT) < 0.01:
            return f"{loc} — Sleeper Berth: Split provision short period (2h, 49 CFR 395.1(g))"
        else:
            return f"{loc} — Sleeper Berth: {int(duration)}h rest"

    _REMARK_MAP = {
        "pre_trip": lambda loc: f"{loc} — On Duty: Pre-trip inspection",
        "pickup":   lambda loc: f"{loc} — On Duty: Pickup, loading and paperwork",
        "dropoff":  lambda loc: f"{loc} — On Duty: Dropoff, unloading and paperwork",
        "rest":     lambda loc: f"{loc} — Off Duty: 30-minute mandatory break",
        "fuel":     lambda loc: f"{loc} — On Duty: Fuel stop",
        "sleeper":  _sleeper_remark,
    }

    builder = _REMARK_MAP.get(stop_type)
    if not builder or not location:
        return ""
    return builder(location)


def _segment(status: str, label: str, start: float, end: float) -> dict:
    return {
        "status": status,
        "label": label,
        "start": round(start, 2),
        "end": round(end, 2),
    }
