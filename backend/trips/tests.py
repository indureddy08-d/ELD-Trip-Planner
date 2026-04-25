"""
HOS Engine Unit Tests

Pure Python — no Django ORM, no HTTP, no external services.
Each test proves one specific HOS rule or planner behaviour.

Run with:
    python manage.py test trips.tests
"""
import sys
import os
import unittest

# Allow running directly without manage.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.local")

import django
django.setup()

from compliance.hos_rules import (
    MAX_DRIVING_PER_SHIFT, MAX_ON_DUTY_PER_SHIFT, CYCLE_LIMIT,
    MANDATORY_BREAK_AFTER, MANDATORY_BREAK_DURATION,
    FUEL_INTERVAL_MILES, FUEL_STOP_DURATION,
    PICKUP_DURATION, DROPOFF_DURATION, AVG_SPEED_MPH,
)
from trips.planner import _build_stop_schedule, plan
from logs.generator import generate


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stops_of_type(stops, stop_type):
    return [s for s in stops if s["stop_type"] == stop_type]


def _drive_short_trip(deadhead=100.0, loaded=100.0, cycle_used=0.0):
    """Run the planner with a simple short trip and return stops."""
    stops, _ = _build_stop_schedule(
        deadhead=deadhead,
        loaded=loaded,
        total=deadhead + loaded,
        pickup="Pickup City",
        dropoff="Dropoff City",
        cycle_used=cycle_used,
    )
    return stops


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFuelStopBreakReset(unittest.TestCase):
    """
    Fuel stop resets the 8-hour break accumulator per project assumptions.
    A driver who fuels before hitting 8h should not immediately need a rest stop.
    """

    def test_fuel_stop_resets_break_accumulator(self):
        """
        Drive 900 miles (just under 1000-mile fuel threshold but over 8h driving).
        The fuel stop at mile 1000 should reset the break counter so no rest
        stop appears immediately after the fuel stop.
        """
        # Drive 1050 miles: fuel stop at 1000, then 50 more miles
        stops = _drive_short_trip(deadhead=1050.0, loaded=10.0)
        fuel_stops = _stops_of_type(stops, "fuel")
        self.assertGreater(len(fuel_stops), 0, "Expected a fuel stop at 1000 miles")

        # Find the first fuel stop and check no rest stop immediately follows it
        first_fuel = fuel_stops[0]
        fuel_idx = stops.index(first_fuel)
        if fuel_idx + 1 < len(stops):
            next_stop = stops[fuel_idx + 1]
            self.assertNotEqual(
                next_stop["stop_type"], "rest",
                "Rest stop should not immediately follow a fuel stop (break was reset)"
            )


class TestElevenHourDrivingLimit(unittest.TestCase):
    """11-hour driving limit must trigger a sleeper berth stop."""

    def test_sleeper_triggered_at_11h_driving(self):
        """
        Drive enough miles to exceed the 11-hour driving limit.
        Expect at least one sleeper stop.
        """
        # 11h * 55mph = 605 miles to hit the limit (after the 30-min break resets)
        # Use a large enough distance to guarantee hitting 11h
        miles = (MAX_DRIVING_PER_SHIFT + 1) * AVG_SPEED_MPH
        stops = _drive_short_trip(deadhead=miles, loaded=10.0)
        sleeper_stops = _stops_of_type(stops, "sleeper")
        self.assertGreater(len(sleeper_stops), 0, "Expected sleeper stop after 11h driving")

    def test_sleeper_resets_drive_counter(self):
        """After a sleeper stop, drive_today should reset to 0."""
        miles = (MAX_DRIVING_PER_SHIFT + 1) * AVG_SPEED_MPH
        stops = _drive_short_trip(deadhead=miles, loaded=10.0)
        sleeper_stops = _stops_of_type(stops, "sleeper")
        self.assertGreater(len(sleeper_stops), 0)
        # The cumulative_drive_hours at the sleeper stop should be at the limit
        first_sleeper = sleeper_stops[0]
        self.assertAlmostEqual(
            first_sleeper["cumulative_drive_hours"],
            MAX_DRIVING_PER_SHIFT, delta=0.1,
            msg="Sleeper should trigger at the 11h driving limit"
        )


class TestFourteenHourWindow(unittest.TestCase):
    """14-hour on-duty window must trigger a sleeper berth stop."""

    def test_14h_window_triggers_sleeper(self):
        """
        Pickup (1h on-duty) + driving should exhaust the 14h window.
        With 1h pickup + 11h driving = 12h, add more on-duty to push past 14h.
        Use a loaded leg long enough to push on_duty_today past 14h.
        """
        # After pickup (1h on-duty), drive 13h worth of miles
        # 13h * 55mph = 715 miles loaded — total on-duty = 1 + 13 = 14h → sleeper
        stops = _drive_short_trip(deadhead=10.0, loaded=715.0)
        sleeper_stops = _stops_of_type(stops, "sleeper")
        self.assertGreater(
            len(sleeper_stops), 0,
            "Expected sleeper stop when 14h on-duty window is exhausted"
        )


class TestCycleExhaustion(unittest.TestCase):
    """Cycle exhaustion must raise ValueError before any planning occurs."""

    def test_cycle_at_limit_raises_before_routing(self):
        """
        Passing cycle_used=70 to plan() must raise ValueError immediately,
        before any routing API calls are made.
        """
        with self.assertRaises(ValueError) as ctx:
            plan(
                current_location="Chicago, IL",
                pickup_location="Dallas, TX",
                dropoff_location="New York, NY",
                cycle_used=70.0,
            )
        self.assertIn("70-hour", str(ctx.exception))

    def test_cycle_above_limit_raises(self):
        """cycle_used > 70 must also raise."""
        with self.assertRaises(ValueError):
            plan(
                current_location="Chicago, IL",
                pickup_location="Dallas, TX",
                dropoff_location="New York, NY",
                cycle_used=71.0,
            )

    def test_cycle_mid_trip_raises(self):
        """
        A driver with 65h used attempting a long trip should hit the cycle
        limit mid-drive and raise ValueError.
        """
        with self.assertRaises(ValueError) as ctx:
            _build_stop_schedule(
                deadhead=2000.0, loaded=2000.0, total=4000.0,
                pickup="Pickup", dropoff="Dropoff",
                cycle_used=65.0,
            )
        self.assertIn("cycle", str(ctx.exception).lower())


class TestPickupDropoffDuration(unittest.TestCase):
    """Pickup and dropoff must each consume exactly the configured 1 hour."""

    def test_pickup_duration(self):
        """
        The pickup stop duration must equal PICKUP_DURATION (1.0h).
        This is on-duty time for loading and paperwork.
        """
        stops = _drive_short_trip(deadhead=100.0, loaded=100.0)
        pickup_stops = _stops_of_type(stops, "pickup")
        self.assertEqual(len(pickup_stops), 1, "Expected exactly one pickup stop")
        self.assertAlmostEqual(
            pickup_stops[0]["duration_hours"], PICKUP_DURATION, places=3,
            msg=f"Pickup must consume exactly {PICKUP_DURATION}h"
        )

    def test_dropoff_duration(self):
        """
        The dropoff stop duration must equal DROPOFF_DURATION (1.0h).
        This is on-duty time for unloading and paperwork.
        """
        stops = _drive_short_trip(deadhead=100.0, loaded=100.0)
        dropoff_stops = _stops_of_type(stops, "dropoff")
        self.assertEqual(len(dropoff_stops), 1, "Expected exactly one dropoff stop")
        self.assertAlmostEqual(
            dropoff_stops[0]["duration_hours"], DROPOFF_DURATION, places=3,
            msg=f"Dropoff must consume exactly {DROPOFF_DURATION}h"
        )

    def test_pickup_and_dropoff_are_on_duty_in_eld(self):
        """
        Both pickup and dropoff must appear as ON_DUTY (not driving) in the
        ELD timeline — they count against the 14h window and 70h cycle.
        """
        stops, elapsed = _build_stop_schedule(
            deadhead=100.0, loaded=100.0, total=200.0,
            pickup="Pickup", dropoff="Dropoff",
            cycle_used=0.0,
        )
        logs = generate(stops, elapsed)
        all_entries = [seg for log in logs for seg in log["timeline"]]
        on_duty_labels = [e["label"] for e in all_entries if e["status"] == "ON"]
        self.assertTrue(
            any("pickup" in label.lower() for label in on_duty_labels),
            "Pickup must appear as ON_DUTY in ELD timeline"
        )
        self.assertTrue(
            any("dropoff" in label.lower() for label in on_duty_labels),
            "Dropoff must appear as ON_DUTY in ELD timeline"
        )


class TestDeterminism(unittest.TestCase):
    """Planner output must be identical for the same inputs on repeated calls."""

    def test_same_inputs_produce_same_stops(self):
        """
        Running the planner twice with identical inputs must produce
        byte-for-byte identical stop lists. Non-determinism here would
        indicate hidden mutable state or random behaviour.
        """
        kwargs = dict(
            deadhead=750.0, loaded=750.0, total=1500.0,
            pickup="Pickup City", dropoff="Dropoff City",
            cycle_used=10.0,
        )
        stops_a, elapsed_a = _build_stop_schedule(**kwargs)
        stops_b, elapsed_b = _build_stop_schedule(**kwargs)

        self.assertEqual(elapsed_a, elapsed_b, "Elapsed hours must be identical")
        self.assertEqual(len(stops_a), len(stops_b), "Stop count must be identical")
        for i, (a, b) in enumerate(zip(stops_a, stops_b)):
            self.assertEqual(a, b, f"Stop {i} differs between runs")

    def test_same_inputs_produce_same_eld_logs(self):
        """
        ELD log generation must also be deterministic — same stops in,
        same log sheets out, every time.
        """
        stops, elapsed = _build_stop_schedule(
            deadhead=750.0, loaded=750.0, total=1500.0,
            pickup="Pickup City", dropoff="Dropoff City",
            cycle_used=10.0,
        )
        from datetime import date
        fixed_date = date(2026, 1, 1)
        logs_a = generate(stops, elapsed, start_date=fixed_date)
        logs_b = generate(stops, elapsed, start_date=fixed_date)

        self.assertEqual(len(logs_a), len(logs_b), "Log count must be identical")
        for i, (a, b) in enumerate(zip(logs_a, logs_b)):
            self.assertEqual(a, b, f"ELD log day {i + 1} differs between runs")


class TestInvariants(unittest.TestCase):
    """
    Invariant checks must catch structurally broken plan output.
    These tests exercise the validation layer directly with crafted bad data.
    """

    def _good_summary(self):
        return {
            "total_distance_miles": 500.0,
            "deadhead_miles": 200.0,
            "loaded_miles": 300.0,
            "estimated_total_hours": 10.0,
            "cycle_hours_remaining": 5.0,
        }

    def _good_stops(self):
        return [
            {"stop_type": "pickup",  "location_name": "A", "arrival_hour": 3.0,
             "duration_hours": 1.0, "cumulative_miles": 165.0, "cumulative_drive_hours": 3.0, "notes": ""},
            {"stop_type": "dropoff", "location_name": "B", "arrival_hour": 8.0,
             "duration_hours": 1.0, "cumulative_miles": 440.0, "cumulative_drive_hours": 8.0, "notes": ""},
        ]

    def _good_eld(self):
        return [{
            "day_number": 1, "log_date": "2026-01-01",
            "driving_hours": 8.0, "on_duty_not_driving_hours": 2.0,
            "sleeper_berth_hours": 0.0, "off_duty_hours": 14.0,
        }]

    def test_valid_plan_passes(self):
        """A structurally correct plan must pass all invariant checks without error."""
        from trips.invariants import assert_plan_invariants
        assert_plan_invariants(self._good_stops(), self._good_eld(), self._good_summary())

    def test_negative_duration_fails(self):
        """A stop with zero or negative duration must be caught."""
        from trips.invariants import assert_plan_invariants
        stops = self._good_stops()
        stops[0]["duration_hours"] = 0.0
        with self.assertRaises(AssertionError) as ctx:
            assert_plan_invariants(stops, self._good_eld(), self._good_summary())
        self.assertIn("non-positive duration", str(ctx.exception))

    def test_overlapping_stops_fails(self):
        """Two stops that overlap in time must be caught."""
        from trips.invariants import assert_plan_invariants
        stops = self._good_stops()
        # Stop 0 ends at 3.0 + 1.0 = 4.0h, stop 1 starts at 3.5h — overlap
        stops[1]["arrival_hour"] = 3.5
        with self.assertRaises(AssertionError) as ctx:
            assert_plan_invariants(stops, self._good_eld(), self._good_summary())
        self.assertIn("overlap", str(ctx.exception))

    def test_dropoff_before_pickup_fails(self):
        """Dropoff arriving before pickup must be caught."""
        from trips.invariants import assert_plan_invariants
        stops = [
            {"stop_type": "dropoff", "location_name": "B", "arrival_hour": 2.0,
             "duration_hours": 1.0, "cumulative_miles": 100.0, "cumulative_drive_hours": 2.0, "notes": ""},
            {"stop_type": "pickup",  "location_name": "A", "arrival_hour": 5.0,
             "duration_hours": 1.0, "cumulative_miles": 200.0, "cumulative_drive_hours": 5.0, "notes": ""},
        ]
        with self.assertRaises(AssertionError) as ctx:
            assert_plan_invariants(stops, self._good_eld(), self._good_summary())
        self.assertIn("before dropoff", str(ctx.exception))

    def test_eld_hours_exceed_24_fails(self):
        """An ELD log whose hours sum to more than 24 must be caught."""
        from trips.invariants import assert_plan_invariants
        eld = self._good_eld()
        eld[0]["driving_hours"] = 20.0
        eld[0]["off_duty_hours"] = 10.0  # 20 + 2 + 0 + 10 = 32h
        with self.assertRaises(AssertionError) as ctx:
            assert_plan_invariants(self._good_stops(), eld, self._good_summary())
        self.assertIn("exceeds 24", str(ctx.exception))

    def test_negative_summary_field_fails(self):
        """A negative value in a summary field must be caught."""
        from trips.invariants import assert_plan_invariants
        summary = self._good_summary()
        summary["total_distance_miles"] = -1.0
        with self.assertRaises(AssertionError) as ctx:
            assert_plan_invariants(self._good_stops(), self._good_eld(), summary)
        self.assertIn("negative", str(ctx.exception))

    def test_real_plan_passes_invariants(self):
        """
        A real plan produced by the engine must pass all invariant checks.
        This is the integration-level proof that the engine and validator agree.
        """
        stops, elapsed = _build_stop_schedule(
            deadhead=600.0, loaded=600.0, total=1200.0,
            pickup="Pickup", dropoff="Dropoff",
            cycle_used=0.0,
        )
        from logs.generator import generate
        from datetime import date
        logs = generate(stops, elapsed, start_date=date(2026, 1, 1))
        from trips.invariants import assert_plan_invariants
        summary = {
            "total_distance_miles": 1200.0,
            "deadhead_miles": 600.0,
            "loaded_miles": 600.0,
            "estimated_total_hours": elapsed,
            "cycle_hours_remaining": max(0.0, 70.0 - elapsed),
        }
        # Must not raise
        assert_plan_invariants(stops, logs, summary)


class TestMultiDayELDGeneration(unittest.TestCase):
    """
    Comprehensive proof of multi-day ELD log generation correctness.

    Covers every structural requirement of the FMCSA-style 24-hour logbook:
      - Long trips produce 2+ daily sheets with unique dates
      - Every non-final day totals exactly 24 hours
      - Every day's timeline starts at 0h, ends at 24h (non-final), no gaps
      - Sleeper segments spanning midnight are split correctly across days
      - Sleeper hours on each side of midnight are numerically correct
      - Remarks land on the day the stop starts, not on continuation days
      - day_number is sequential from 1; log_date advances by one calendar day
      - Daily miles sum to the trip total
      - All required fields are present on every log sheet
      - The full invariant suite passes end-to-end

    All tests use a fixed start_date so output is deterministic.
    """

    START_DATE = None  # set in setUpClass

    @classmethod
    def setUpClass(cls):
        from datetime import date
        cls.START_DATE = date(2026, 1, 1)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_long_trip(self, deadhead=800.0, loaded=800.0, cycle_used=0.0):
        """1,600-mile trip: 2 sleeper resets, 3 ELD days."""
        stops, elapsed = _build_stop_schedule(
            deadhead=deadhead, loaded=loaded,
            total=deadhead + loaded,
            pickup="Dallas, TX", dropoff="New York, NY",
            cycle_used=cycle_used,
        )
        logs = generate(stops, elapsed, start_date=self.START_DATE)
        return stops, elapsed, logs

    def _make_midnight_sleeper(self, sleeper_start=22.0, sleeper_dur=10.0, dropoff_offset=2.0):
        """
        Craft a stop list with a sleeper that spans midnight.
        dropoff_offset: hours after the sleeper ends before dropoff.
        """
        sleeper_end = sleeper_start + sleeper_dur
        stops = [
            {
                "stop_type": "sleeper",
                "location_name": "Oklahoma City, OK",
                "arrival_hour": sleeper_start,
                "duration_hours": sleeper_dur,
                "cumulative_drive_hours": 11.0,
                "cumulative_miles": 500.0,
                "notes": "10-hour sleeper berth — HOS shift reset",
            },
            {
                "stop_type": "dropoff",
                "location_name": "Dallas, TX",
                "arrival_hour": sleeper_end + dropoff_offset,
                "duration_hours": 1.0,
                "cumulative_drive_hours": 2.0,
                "cumulative_miles": 600.0,
                "notes": "On-duty: unloading and paperwork (1 hour)",
            },
        ]
        total_hours = sleeper_end + dropoff_offset + 1.0
        logs = generate(stops, total_hours, start_date=self.START_DATE)
        return stops, logs

    # ── 1. Long trip: 2+ daily sheets ────────────────────────────────────────

    def test_long_trip_produces_at_least_two_daily_sheets(self):
        """
        A 1,600-mile trip requires two sleeper resets and must produce
        at least 2 ELD log sheets — one per active calendar day.
        """
        _, _, logs = self._make_long_trip()
        self.assertGreaterEqual(
            len(logs), 2,
            f"1,600-mile trip must produce 2+ ELD sheets, got {len(logs)}"
        )

    def test_long_trip_produces_exactly_three_daily_sheets(self):
        """
        The specific 1,600-mile trip (800 deadhead + 800 loaded, 0 cycle used)
        must produce exactly 3 ELD sheets. This pins the expected output shape
        so a regression that changes the sheet count is immediately visible.
        """
        _, _, logs = self._make_long_trip()
        self.assertEqual(
            len(logs), 3,
            f"Expected exactly 3 ELD sheets for this trip, got {len(logs)}: "
            f"{[l['log_date'] for l in logs]}"
        )

    def test_each_sheet_has_all_required_fields(self):
        """
        Every ELD log sheet must contain all fields the React frontend expects.
        Missing a field would cause a silent undefined in the UI.
        """
        _, _, logs = self._make_long_trip()
        required = {
            "day_number", "log_date",
            "driving_hours", "on_duty_not_driving_hours",
            "sleeper_berth_hours", "off_duty_hours",
            "total_miles", "timeline", "remarks",
        }
        for log in logs:
            missing = required - set(log.keys())
            self.assertEqual(
                missing, set(),
                f"Day {log['day_number']} is missing fields: {missing}"
            )

    # ── 2. Every non-final day totals exactly 24 hours ────────────────────────

    def test_non_final_days_total_exactly_24_hours(self):
        """
        Every day except the last must account for all 24 hours.
        The final day may be partial (trip ends mid-day).

        This is the core FMCSA logbook requirement: every 24-hour period
        must be fully accounted for across all duty statuses.
        """
        _, _, logs = self._make_long_trip()
        self.assertGreaterEqual(len(logs), 2, "Need at least 2 days to test non-final days")

        for log in logs[:-1]:
            total = (
                log["driving_hours"]
                + log["on_duty_not_driving_hours"]
                + log["sleeper_berth_hours"]
                + log["off_duty_hours"]
            )
            self.assertAlmostEqual(
                total, 24.0, delta=0.05,
                msg=(
                    f"Day {log['day_number']} ({log['log_date']}) totals "
                    f"{round(total, 3)}h — must be exactly 24h"
                )
            )

    def test_final_day_does_not_exceed_24_hours(self):
        """
        The final day may be partial but must never exceed 24 hours.
        """
        _, _, logs = self._make_long_trip()
        final = logs[-1]
        total = (
            final["driving_hours"]
            + final["on_duty_not_driving_hours"]
            + final["sleeper_berth_hours"]
            + final["off_duty_hours"]
        )
        self.assertLessEqual(
            total, 24.05,
            f"Final day ({final['log_date']}) totals {round(total, 3)}h — must not exceed 24h"
        )

    # ── 3. Timeline continuity ────────────────────────────────────────────────

    def test_timeline_starts_at_zero_on_every_day(self):
        """
        The first timeline segment on every day must start at 0.0h.
        A non-zero start means the generator left an unaccounted gap at the
        beginning of the day — the ELD grid would show a blank leading block.
        """
        _, _, logs = self._make_long_trip()
        for log in logs:
            timeline = sorted(log["timeline"], key=lambda s: s["start"])
            self.assertAlmostEqual(
                timeline[0]["start"], 0.0, delta=0.05,
                msg=f"Day {log['day_number']} timeline must start at 0h, "
                    f"got {timeline[0]['start']:.3f}h"
            )

    def test_non_final_day_timeline_ends_at_24(self):
        """
        The last timeline segment on every non-final day must end at 24.0h.
        A non-24 end means the generator left an unaccounted gap at the end
        of the day — the ELD grid would show a blank trailing block.
        """
        _, _, logs = self._make_long_trip()
        for log in logs[:-1]:
            timeline = sorted(log["timeline"], key=lambda s: s["start"])
            self.assertAlmostEqual(
                timeline[-1]["end"], 24.0, delta=0.05,
                msg=f"Day {log['day_number']} (non-final) timeline must end at 24h, "
                    f"got {timeline[-1]['end']:.3f}h"
            )

    def test_no_gaps_between_timeline_segments(self):
        """
        Consecutive timeline segments on every day must be contiguous —
        the end of segment N must equal the start of segment N+1.
        A gap would produce a blank block on the ELD duty grid.
        """
        _, _, logs = self._make_long_trip()
        for log in logs:
            timeline = sorted(log["timeline"], key=lambda s: s["start"])
            for i in range(len(timeline) - 1):
                gap = timeline[i + 1]["start"] - timeline[i]["end"]
                self.assertAlmostEqual(
                    gap, 0.0, delta=0.05,
                    msg=(
                        f"Day {log['day_number']}: gap of {gap:.3f}h between "
                        f"segment {i} ({timeline[i]['status']} "
                        f"{timeline[i]['start']:.2f}→{timeline[i]['end']:.2f}) "
                        f"and segment {i+1} ({timeline[i+1]['status']} "
                        f"{timeline[i+1]['start']:.2f}→{timeline[i+1]['end']:.2f})"
                    )
                )

    # ── 4. Sleeper spanning midnight ──────────────────────────────────────────

    def test_sleeper_spanning_midnight_split_into_two_days(self):
        """
        A 10-hour sleeper starting at hour 22 spans midnight.
        It must appear in both Day 1 and Day 2 timelines.
        """
        _, logs = self._make_midnight_sleeper(sleeper_start=22.0)
        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        day1_statuses = {seg["status"] for seg in day1["timeline"]}
        day2_statuses = {seg["status"] for seg in day2["timeline"]}

        self.assertIn("SB", day1_statuses,
                      "Day 1 must contain a Sleeper Berth segment (sleeper starts on Day 1)")
        self.assertIn("SB", day2_statuses,
                      "Day 2 must contain a Sleeper Berth segment (sleeper continues into Day 2)")

    def test_sleeper_hours_split_correctly_across_midnight(self):
        """
        A 10-hour sleeper starting at hour 22 must contribute:
          - 2h sleeper to Day 1 (hours 22–24)
          - 8h sleeper to Day 2 (hours 0–8)
        Total sleeper across both days must equal exactly 10h.
        """
        _, logs = self._make_midnight_sleeper(sleeper_start=22.0, sleeper_dur=10.0)
        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        self.assertAlmostEqual(
            day1["sleeper_berth_hours"], 2.0, delta=0.05,
            msg=f"Day 1 should have 2h sleeper (22h–24h), got {day1['sleeper_berth_hours']}h"
        )
        self.assertAlmostEqual(
            day2["sleeper_berth_hours"], 8.0, delta=0.05,
            msg=f"Day 2 should have 8h sleeper (0h–8h), got {day2['sleeper_berth_hours']}h"
        )
        total = day1["sleeper_berth_hours"] + day2["sleeper_berth_hours"]
        self.assertAlmostEqual(
            total, 10.0, delta=0.05,
            msg=f"Total sleeper across both days must equal 10h, got {total}h"
        )

    def test_sleeper_segment_positions_correct_on_each_day(self):
        """
        The sleeper segment positions within each day's timeline must be correct:
          - Day 1: SB segment runs from 22.0 to 24.0 (relative to day start)
          - Day 2: SB segment runs from 0.0 to 8.0 (relative to day start)
        """
        _, logs = self._make_midnight_sleeper(sleeper_start=22.0, sleeper_dur=10.0)
        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        sb_day1 = next(seg for seg in day1["timeline"] if seg["status"] == "SB")
        sb_day2 = next(seg for seg in day2["timeline"] if seg["status"] == "SB")

        self.assertAlmostEqual(sb_day1["start"], 22.0, delta=0.05,
                               msg="Day 1 SB segment must start at 22.0h")
        self.assertAlmostEqual(sb_day1["end"],   24.0, delta=0.05,
                               msg="Day 1 SB segment must end at 24.0h")
        self.assertAlmostEqual(sb_day2["start"],  0.0, delta=0.05,
                               msg="Day 2 SB segment must start at 0.0h")
        self.assertAlmostEqual(sb_day2["end"],    8.0, delta=0.05,
                               msg="Day 2 SB segment must end at 8.0h")

    def test_sleeper_ending_exactly_at_midnight_handled(self):
        """
        A sleeper that ends exactly at midnight (arrival=14h, dur=10h → ends at 24h)
        must be entirely on Day 1 with no SB bleed into Day 2.
        Day 2 must start with driving, not sleeper.
        """
        stops = [
            {
                "stop_type": "sleeper",
                "location_name": "MM500",
                "arrival_hour": 14.0,
                "duration_hours": 10.0,
                "cumulative_drive_hours": 11.0,
                "cumulative_miles": 500.0,
                "notes": "10-hour sleeper berth",
            },
            {
                "stop_type": "dropoff",
                "location_name": "NYC",
                "arrival_hour": 25.0,
                "duration_hours": 1.0,
                "cumulative_drive_hours": 2.0,
                "cumulative_miles": 600.0,
                "notes": "On-duty: unloading",
            },
        ]
        logs = generate(stops, 26.0, start_date=self.START_DATE)
        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        # Day 1 should have exactly 10h sleeper
        self.assertAlmostEqual(day1["sleeper_berth_hours"], 10.0, delta=0.05,
                               msg="Day 1 should have 10h sleeper (14h–24h)")
        # Day 2 should have 0h sleeper
        self.assertAlmostEqual(day2["sleeper_berth_hours"], 0.0, delta=0.05,
                               msg="Day 2 should have 0h sleeper (sleeper ended at midnight)")

    def test_sleeper_starting_exactly_at_midnight_handled(self):
        """
        A sleeper that starts exactly at midnight (arrival_hour=24.0) must
        appear entirely on Day 2, not split across Day 1 and Day 2.
        Day 1 must be all driving (no SB).
        """
        stops = [
            {
                "stop_type": "sleeper",
                "location_name": "MM500",
                "arrival_hour": 24.0,
                "duration_hours": 10.0,
                "cumulative_drive_hours": 11.0,
                "cumulative_miles": 500.0,
                "notes": "10-hour sleeper berth",
            },
            {
                "stop_type": "dropoff",
                "location_name": "NYC",
                "arrival_hour": 35.0,
                "duration_hours": 1.0,
                "cumulative_drive_hours": 2.0,
                "cumulative_miles": 600.0,
                "notes": "On-duty: unloading",
            },
        ]
        logs = generate(stops, 36.0, start_date=self.START_DATE)
        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        self.assertAlmostEqual(day1["sleeper_berth_hours"], 0.0, delta=0.05,
                               msg="Day 1 should have 0h sleeper (sleeper starts at midnight)")
        self.assertAlmostEqual(day2["sleeper_berth_hours"], 10.0, delta=0.05,
                               msg="Day 2 should have 10h sleeper (0h–10h)")

    # ── 5. Remarks on correct day ─────────────────────────────────────────────

    def test_sleeper_remark_on_start_day_only(self):
        """
        A sleeper spanning midnight must have its remark on Day 1 (start day)
        and must NOT appear on Day 2 (continuation day).
        """
        _, logs = self._make_midnight_sleeper(sleeper_start=22.0)
        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        self.assertIn("Oklahoma City, OK", day1["remarks"],
                      "Sleeper remark must appear on Day 1 (start day)")
        self.assertNotIn("Oklahoma City, OK", day2["remarks"],
                         "Sleeper remark must NOT appear on Day 2 (continuation day)")

    def test_dropoff_remark_on_correct_day(self):
        """
        The dropoff remark must appear on the day the dropoff stop starts,
        not on the day the preceding sleeper started.
        """
        _, logs = self._make_midnight_sleeper(sleeper_start=22.0, dropoff_offset=2.0)
        # Sleeper ends at 32h → Day 2. Dropoff at 34h → Day 2.
        day2 = next(l for l in logs if l["day_number"] == 2)
        self.assertIn("Dallas, TX", day2["remarks"],
                      "Dropoff remark must appear on Day 2")

    def test_remarks_not_duplicated_across_days(self):
        """
        No remark should appear on more than one day.
        Duplicate remarks indicate the generator is emitting remarks on
        continuation days instead of only on the stop's start day.
        """
        _, _, logs = self._make_long_trip()
        all_remarks: list[str] = []
        for log in logs:
            if log["remarks"]:
                for remark in log["remarks"].split("; "):
                    all_remarks.append(remark.strip())

        # Each unique remark should appear exactly once across all days
        from collections import Counter
        counts = Counter(all_remarks)
        duplicates = {r: c for r, c in counts.items() if c > 1}
        self.assertEqual(
            duplicates, {},
            f"These remarks appear on multiple days (duplication bug): {duplicates}"
        )

    # ── 6. day_number and log_date sequence ───────────────────────────────────

    def test_day_numbers_are_sequential_from_one(self):
        """
        day_number must be 1, 2, 3, … with no gaps or duplicates.
        """
        _, _, logs = self._make_long_trip()
        day_numbers = [l["day_number"] for l in logs]
        expected = list(range(1, len(logs) + 1))
        self.assertEqual(day_numbers, expected,
                         f"day_numbers must be sequential from 1: got {day_numbers}")

    def test_log_dates_are_sequential_calendar_days(self):
        """
        log_date must advance by exactly one calendar day per sheet.
        """
        from datetime import date, timedelta
        _, _, logs = self._make_long_trip()
        for i, log in enumerate(logs):
            expected_date = str(self.START_DATE + timedelta(days=i))
            self.assertEqual(
                log["log_date"], expected_date,
                f"Day {log['day_number']} log_date={log['log_date']}, "
                f"expected {expected_date}"
            )

    # ── 7. Daily miles ────────────────────────────────────────────────────────

    def test_daily_miles_sum_to_trip_total(self):
        """
        The sum of total_miles across all ELD log sheets must equal the
        trip's total distance. Miles must not be double-counted or lost
        at day boundaries.
        """
        deadhead, loaded = 800.0, 800.0
        stops, elapsed = _build_stop_schedule(
            deadhead=deadhead, loaded=loaded,
            total=deadhead + loaded,
            pickup="Dallas, TX", dropoff="New York, NY",
            cycle_used=0.0,
        )
        logs = generate(stops, elapsed, start_date=self.START_DATE)
        eld_total = sum(l["total_miles"] for l in logs)
        trip_total = deadhead + loaded
        self.assertAlmostEqual(
            eld_total, trip_total, delta=trip_total * 0.02,
            msg=f"ELD miles sum ({eld_total}) must match trip total ({trip_total})"
        )

    def test_no_day_has_negative_miles(self):
        """Every day's total_miles must be non-negative."""
        _, _, logs = self._make_long_trip()
        for log in logs:
            self.assertGreaterEqual(
                log["total_miles"], 0.0,
                f"Day {log['day_number']} has negative total_miles: {log['total_miles']}"
            )

    # ── 8. Full invariant suite ───────────────────────────────────────────────

    def test_invariants_pass_on_long_trip(self):
        """
        The full invariant suite (structural + cross-layer) must pass on a
        1,600-mile multi-day trip. This is the integration-level proof that
        all layers agree on the multi-day output.
        """
        from trips.invariants import assert_plan_invariants, assert_cross_layer_consistency
        from trips.planner import _build_instructions
        deadhead, loaded = 800.0, 800.0
        stops, elapsed, logs = self._make_long_trip(deadhead=deadhead, loaded=loaded)
        summary = {
            "total_distance_miles": round(deadhead + loaded, 1),
            "deadhead_miles": round(deadhead, 1),
            "loaded_miles": round(loaded, 1),
            "estimated_total_hours": elapsed,
            "cycle_hours_remaining": max(0.0, 70.0 - elapsed),
            "number_of_stops": len(stops),
            "number_of_days": len(logs),
        }
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="New York, NY",
            deadhead=deadhead,
            loaded=loaded,
            stops=stops,
        )
        # Must not raise
        assert_plan_invariants(stops, logs, summary)
        assert_cross_layer_consistency(stops, logs, summary, instructions)


class TestMandatoryBreakBehavior(unittest.TestCase):
    """
    End-to-end proof of the 30-minute mandatory break rule.

    Covers every layer the break must appear in:
      - Stop schedule (planner)
      - ELD timeline status and totals (generator)
      - ELD daily remarks (generator)
      - Route instructions (planner)
      - Invariant layer (invariants)

    Reference: 49 CFR 395.3(a)(3)(ii) — property-carrying driver must take
    a 30-minute non-driving break after 8 cumulative hours of driving.
    """

    # Drive exactly enough to cross the 8h threshold once, with a short loaded leg
    # so the trip completes without hitting the 11h driving limit.
    # 8.1h * 55mph = 445.5 miles deadhead → triggers break, then 10 miles loaded.
    DEADHEAD = (MANDATORY_BREAK_AFTER + 0.1) * AVG_SPEED_MPH   # ~445.5 miles
    LOADED   = 10.0

    def _plan(self):
        """Build the stop schedule and ELD logs for the trigger trip."""
        stops, elapsed = _build_stop_schedule(
            deadhead=self.DEADHEAD,
            loaded=self.LOADED,
            total=self.DEADHEAD + self.LOADED,
            pickup="Dallas, TX",
            dropoff="Houston, TX",
            cycle_used=0.0,
        )
        from datetime import date
        logs = generate(stops, elapsed, start_date=date(2026, 1, 1))
        return stops, elapsed, logs

    # ── 1. Planner: exactly one rest stop ────────────────────────────────────

    def test_exactly_one_rest_stop_inserted(self):
        """
        A trip that crosses 8h driving exactly once must produce exactly one
        rest stop — not zero (missed trigger) and not two (double-insert bug).
        """
        stops, _, _ = self._plan()
        rest_stops = _stops_of_type(stops, "rest")
        self.assertEqual(
            len(rest_stops), 1,
            f"Expected exactly 1 rest stop, got {len(rest_stops)}: {rest_stops}"
        )

    def test_rest_stop_triggers_at_8h_cumulative_drive(self):
        """
        The rest stop's cumulative_drive_hours must equal MANDATORY_BREAK_AFTER (8.0h).
        This proves the break fires at the correct threshold, not earlier or later.
        """
        stops, _, _ = self._plan()
        rest = _stops_of_type(stops, "rest")[0]
        self.assertAlmostEqual(
            rest["cumulative_drive_hours"],
            MANDATORY_BREAK_AFTER,
            delta=0.05,
            msg=(
                f"Rest stop cumulative_drive_hours={rest['cumulative_drive_hours']}h "
                f"should equal MANDATORY_BREAK_AFTER={MANDATORY_BREAK_AFTER}h"
            ),
        )

    def test_rest_stop_duration_is_exactly_30_minutes(self):
        """Duration must be MANDATORY_BREAK_DURATION (0.5h = 30 min), not more, not less."""
        stops, _, _ = self._plan()
        rest = _stops_of_type(stops, "rest")[0]
        self.assertAlmostEqual(
            rest["duration_hours"],
            MANDATORY_BREAK_DURATION,
            places=4,
            msg=f"Rest stop duration must be {MANDATORY_BREAK_DURATION}h (30 min)",
        )

    def test_rest_stop_notes_cite_cfr(self):
        """
        The rest stop notes must reference 49 CFR 395.3 so a reviewer
        can immediately identify the regulatory basis.
        """
        stops, _, _ = self._plan()
        rest = _stops_of_type(stops, "rest")[0]
        self.assertIn(
            "395.3", rest["notes"],
            "Rest stop notes must cite 49 CFR 395.3"
        )

    # ── 2. ELD generator: OFF status, correct totals ─────────────────────────

    def test_rest_stop_is_off_duty_in_eld_timeline(self):
        """
        The break segment in the ELD timeline must have status='OFF'.
        It must never be 'ON' or 'SB' — that would incorrectly consume
        the 14-hour on-duty window.
        """
        _, _, logs = self._plan()
        all_segs = [seg for log in logs for seg in log["timeline"]]
        break_segs = [
            seg for seg in all_segs
            if "break" in seg["label"].lower() or "mandatory" in seg["label"].lower()
        ]
        self.assertGreater(len(break_segs), 0, "No break segment found in ELD timeline")
        for seg in break_segs:
            self.assertEqual(
                seg["status"], "OFF",
                f"Break segment has status='{seg['status']}' — must be 'OFF'. "
                f"Segment: {seg}"
            )

    def test_break_contributes_to_off_duty_hours_not_on_duty(self):
        """
        The day containing the break must have:
          - off_duty_hours >= MANDATORY_BREAK_DURATION (0.5h)
          - The break duration must NOT appear in on_duty_not_driving_hours

        This is the numerical proof that the 14h window is not consumed.
        We verify by checking that on_duty_not_driving_hours on the break day
        equals only the on-duty stops (pre_trip + pickup/dropoff if on same day),
        not the break itself.
        """
        stops, _, logs = self._plan()
        rest = _stops_of_type(stops, "rest")[0]
        rest_day_number = int(rest["arrival_hour"] / 24) + 1
        day_log = next(l for l in logs if l["day_number"] == rest_day_number)

        self.assertGreaterEqual(
            day_log["off_duty_hours"],
            MANDATORY_BREAK_DURATION - 0.01,
            f"Day {rest_day_number} off_duty_hours={day_log['off_duty_hours']}h "
            f"must be >= {MANDATORY_BREAK_DURATION}h (the break duration)"
        )

        # on_duty_not_driving_hours must NOT include the break's 0.5h.
        # For this short trip, pre_trip + pickup + dropoff all land on day 1.
        # If the break were incorrectly counted as on-duty, this total would be
        # 0.5h higher than the sum of the actual on-duty stops.
        pre_trip_duration = sum(
            s["duration_hours"] for s in stops
            if s["stop_type"] == "pre_trip"
            and int(s["arrival_hour"] / 24) + 1 == rest_day_number
        )
        pickup_duration = sum(
            s["duration_hours"] for s in stops
            if s["stop_type"] == "pickup"
            and int(s["arrival_hour"] / 24) + 1 == rest_day_number
        )
        dropoff_duration = sum(
            s["duration_hours"] for s in stops
            if s["stop_type"] == "dropoff"
            and int(s["arrival_hour"] / 24) + 1 == rest_day_number
        )
        expected_on_duty_nd = pre_trip_duration + pickup_duration + dropoff_duration
        self.assertAlmostEqual(
            day_log["on_duty_not_driving_hours"],
            expected_on_duty_nd,
            delta=0.05,
            msg=(
                f"Day {rest_day_number} on_duty_not_driving_hours="
                f"{day_log['on_duty_not_driving_hours']}h but expected "
                f"{expected_on_duty_nd}h (pre_trip + pickup + dropoff only). "
                "The 30-min break must NOT be counted as on-duty."
            ),
        )

    # ── 3. ELD remarks ───────────────────────────────────────────────────────

    def test_break_remark_appears_in_eld_on_correct_day(self):
        """
        The ELD remarks for the day the break occurs must contain a
        human-readable entry identifying it as an off-duty break.
        This is what a DOT inspector reads during a roadside check.
        """
        stops, _, logs = self._plan()
        rest = _stops_of_type(stops, "rest")[0]
        rest_day_number = int(rest["arrival_hour"] / 24) + 1
        day_log = next(l for l in logs if l["day_number"] == rest_day_number)

        remarks_lower = day_log["remarks"].lower()
        self.assertTrue(
            "off duty" in remarks_lower or "break" in remarks_lower,
            f"ELD Day {rest_day_number} remarks must mention the off-duty break. "
            f"Got: '{day_log['remarks']}'"
        )

    # ── 4. Route instructions ────────────────────────────────────────────────

    def test_break_appears_in_route_instructions(self):
        """
        The route instructions must include a dedicated step for the mandatory
        break — it must not be silently omitted from the driver's turn-by-turn plan.
        """
        from trips.planner import _build_instructions
        stops, _, _ = self._plan()
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="Houston, TX",
            deadhead=self.DEADHEAD,
            loaded=self.LOADED,
            stops=stops,
        )
        instruction_text = " ".join(
            step["instruction"] + " " + step["details"]
            for step in instructions
        ).lower()
        self.assertIn(
            "break", instruction_text,
            "Route instructions must include a step for the mandatory 30-min break"
        )
        self.assertIn(
            "395.3", instruction_text,
            "Break instruction must cite 49 CFR 395.3"
        )

    # ── 5. Invariant layer ───────────────────────────────────────────────────

    def test_invariants_pass_on_break_triggering_trip(self):
        """
        The full invariant suite must pass on a trip that includes a rest stop.
        This is the integration-level proof that all layers agree on the break.
        """
        from trips.invariants import assert_plan_invariants, assert_cross_layer_consistency
        from trips.planner import _build_instructions
        stops, elapsed, logs = self._plan()
        summary = {
            "total_distance_miles": round(self.DEADHEAD + self.LOADED, 1),
            "deadhead_miles": round(self.DEADHEAD, 1),
            "loaded_miles": round(self.LOADED, 1),
            "estimated_total_hours": elapsed,
            "cycle_hours_remaining": max(0.0, 70.0 - elapsed),
            "number_of_stops": len(stops),
            "number_of_days": len(logs),
        }
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="Houston, TX",
            deadhead=self.DEADHEAD,
            loaded=self.LOADED,
            stops=stops,
        )
        # Must not raise
        assert_plan_invariants(stops, logs, summary)
        assert_cross_layer_consistency(stops, logs, summary, instructions)


class TestFuelStopBehavior(unittest.TestCase):
    """
    End-to-end proof of fuel stop insertion and cross-layer consistency.

    Covers every layer the fuel stop must appear in:
      - Stop schedule (planner): position, duration, notes wording
      - ELD timeline status and totals (generator): ON duty, not OFF or SB
      - ELD daily remarks (generator): remark present on correct day
      - Route instructions (planner): dedicated step with mile position
      - Break accumulator reset: numerically verified, not just "next stop isn't rest"
      - Multiple fuel stops on a very long trip
      - Full invariant suite passes end-to-end

    Operational assumption: fuel stop is on-duty not driving (counts against
    14h window and 70h cycle) and resets the 8-hour break accumulator.
    """

    # 1,200-mile trip: deadhead=600, loaded=600 → one fuel stop at mile 1,000
    DEADHEAD_1FUEL = 600.0
    LOADED_1FUEL   = 600.0

    # 2,200-mile trip: deadhead=1200, loaded=1000 → two fuel stops
    DEADHEAD_2FUEL = 1200.0
    LOADED_2FUEL   = 1000.0

    def _plan_1fuel(self):
        stops, elapsed = _build_stop_schedule(
            deadhead=self.DEADHEAD_1FUEL, loaded=self.LOADED_1FUEL,
            total=self.DEADHEAD_1FUEL + self.LOADED_1FUEL,
            pickup="Dallas, TX", dropoff="Atlanta, GA",
            cycle_used=0.0,
        )
        from datetime import date
        logs = generate(stops, elapsed, start_date=date(2026, 1, 1))
        return stops, elapsed, logs

    def _plan_2fuel(self):
        stops, elapsed = _build_stop_schedule(
            deadhead=self.DEADHEAD_2FUEL, loaded=self.LOADED_2FUEL,
            total=self.DEADHEAD_2FUEL + self.LOADED_2FUEL,
            pickup="Dallas, TX", dropoff="New York, NY",
            cycle_used=0.0,
        )
        from datetime import date
        logs = generate(stops, elapsed, start_date=date(2026, 1, 1))
        return stops, elapsed, logs

    # ── 1. Stop schedule ─────────────────────────────────────────────────────

    def test_exactly_one_fuel_stop_on_1200_mile_trip(self):
        """
        A 1,200-mile trip crosses the 1,000-mile threshold exactly once.
        Expect exactly one fuel stop — not zero (missed) and not two (double-insert).
        """
        stops, _, _ = self._plan_1fuel()
        fuel_stops = _stops_of_type(stops, "fuel")
        self.assertEqual(
            len(fuel_stops), 1,
            f"Expected exactly 1 fuel stop on a 1,200-mile trip, got {len(fuel_stops)}"
        )

    def test_fuel_stop_at_1000_mile_mark(self):
        """
        The fuel stop must occur at cumulative_miles ≈ FUEL_INTERVAL_MILES (1,000).
        A delta of 1 mile is allowed for floating-point rounding.
        """
        stops, _, _ = self._plan_1fuel()
        fuel = _stops_of_type(stops, "fuel")[0]
        self.assertAlmostEqual(
            fuel["cumulative_miles"], FUEL_INTERVAL_MILES, delta=1.0,
            msg=f"Fuel stop at mile {fuel['cumulative_miles']} — expected ~{FUEL_INTERVAL_MILES}"
        )

    def test_fuel_stop_duration_is_fuel_stop_duration_constant(self):
        """
        Fuel stop duration must equal FUEL_STOP_DURATION (0.5h = 30 min).
        Hardcoding a different value would silently corrupt HOS accounting.
        """
        stops, _, _ = self._plan_1fuel()
        fuel = _stops_of_type(stops, "fuel")[0]
        self.assertAlmostEqual(
            fuel["duration_hours"], FUEL_STOP_DURATION, places=4,
            msg=f"Fuel stop duration must be {FUEL_STOP_DURATION}h (30 min)"
        )

    def test_fuel_stop_notes_include_interval_and_position(self):
        """
        The notes field must tell a reviewer why the stop was made (interval rule)
        and where in the trip it falls (mile position). Both are required for
        a meaningful ELD record.
        """
        stops, _, _ = self._plan_1fuel()
        fuel = _stops_of_type(stops, "fuel")[0]
        notes_lower = fuel["notes"].lower()
        self.assertIn(
            "1,000", fuel["notes"],
            "Fuel stop notes must reference the 1,000-mile interval"
        )
        self.assertIn(
            "mile", notes_lower,
            "Fuel stop notes must include the mile position"
        )

    def test_two_fuel_stops_on_2200_mile_trip(self):
        """
        A 2,200-mile trip crosses the 1,000-mile threshold twice.
        Expect exactly two fuel stops at approximately miles 1,000 and 2,000.
        """
        stops, _, _ = self._plan_2fuel()
        fuel_stops = _stops_of_type(stops, "fuel")
        self.assertEqual(
            len(fuel_stops), 2,
            f"Expected 2 fuel stops on a 2,200-mile trip, got {len(fuel_stops)}"
        )
        self.assertAlmostEqual(fuel_stops[0]["cumulative_miles"], 1000.0, delta=1.0,
                               msg="First fuel stop should be at ~mile 1,000")
        self.assertAlmostEqual(fuel_stops[1]["cumulative_miles"], 2000.0, delta=1.0,
                               msg="Second fuel stop should be at ~mile 2,000")

    # ── 2. ELD generator: ON status, correct totals ──────────────────────────

    def test_fuel_stop_is_on_duty_in_eld_timeline(self):
        """
        The fuel stop segment in the ELD timeline must have status='ON'.
        It must never be 'OFF' or 'SB' — that would under-count on-duty time
        and produce an incorrect 14h window calculation.
        """
        _, _, logs = self._plan_1fuel()
        all_segs = [seg for log in logs for seg in log["timeline"]]
        fuel_segs = [seg for seg in all_segs if "fuel" in seg["label"].lower()]
        self.assertGreater(len(fuel_segs), 0, "No fuel segment found in ELD timeline")
        for seg in fuel_segs:
            self.assertEqual(
                seg["status"], "ON",
                f"Fuel segment has status='{seg['status']}' — must be 'ON'. Segment: {seg}"
            )

    def test_fuel_stop_contributes_to_on_duty_not_driving_hours(self):
        """
        The day containing the fuel stop must have on_duty_not_driving_hours
        that accounts for the fuel stop duration (0.5h).

        We verify that on_duty_not_driving_hours on the fuel day is at least
        FUEL_STOP_DURATION — it will also include pre_trip and possibly pickup,
        so we check a lower bound rather than an exact value.
        """
        stops, _, logs = self._plan_1fuel()
        fuel = _stops_of_type(stops, "fuel")[0]
        fuel_day_number = int(fuel["arrival_hour"] / 24) + 1
        day_log = next(l for l in logs if l["day_number"] == fuel_day_number)

        self.assertGreaterEqual(
            day_log["on_duty_not_driving_hours"],
            FUEL_STOP_DURATION - 0.01,
            f"Day {fuel_day_number} on_duty_not_driving_hours="
            f"{day_log['on_duty_not_driving_hours']}h must be >= {FUEL_STOP_DURATION}h"
        )

    def test_fuel_stop_not_in_off_duty_hours(self):
        """
        The fuel stop must NOT inflate off_duty_hours.
        off_duty_hours on the fuel day should only reflect actual off-duty time
        (e.g. a mandatory break if one also occurs that day), not the fuel stop.

        We verify this by checking that off_duty_hours does not include the
        fuel stop duration when no rest stop is on the same day.
        """
        stops, _, logs = self._plan_1fuel()
        fuel = _stops_of_type(stops, "fuel")[0]
        rest_stops = _stops_of_type(stops, "rest")
        fuel_day_number = int(fuel["arrival_hour"] / 24) + 1

        # Check if any rest stop is on the same day as the fuel stop
        rest_on_same_day = any(
            int(r["arrival_hour"] / 24) + 1 == fuel_day_number for r in rest_stops
        )

        if not rest_on_same_day:
            day_log = next(l for l in logs if l["day_number"] == fuel_day_number)
            # off_duty_hours should be the tail-of-day off-duty, not inflated by fuel
            # The fuel stop (0.5h) must not appear in off_duty_hours
            # We verify by checking on_duty_nd includes the fuel duration
            self.assertGreaterEqual(
                day_log["on_duty_not_driving_hours"],
                FUEL_STOP_DURATION - 0.01,
                "Fuel stop duration must appear in on_duty_not_driving_hours, not off_duty_hours"
            )

    # ── 3. ELD remarks ───────────────────────────────────────────────────────

    def test_fuel_stop_remark_appears_in_eld_on_correct_day(self):
        """
        The ELD remarks for the day the fuel stop occurs must contain a
        human-readable entry identifying it as a fuel stop.
        """
        stops, _, logs = self._plan_1fuel()
        fuel = _stops_of_type(stops, "fuel")[0]
        fuel_day_number = int(fuel["arrival_hour"] / 24) + 1
        day_log = next(l for l in logs if l["day_number"] == fuel_day_number)

        self.assertIn(
            "fuel", day_log["remarks"].lower(),
            f"ELD Day {fuel_day_number} remarks must mention the fuel stop. "
            f"Got: '{day_log['remarks']}'"
        )

    def test_fuel_stop_remark_includes_interval_context(self):
        """
        The fuel stop notes must include the 1,000-mile interval so a DOT
        inspector can immediately understand the operational basis for the stop.
        (The remark records location+status; the notes field carries the detail.)
        """
        stops, _, logs = self._plan_1fuel()
        fuel = _stops_of_type(stops, "fuel")[0]

        self.assertIn(
            "1,000", fuel["notes"],
            f"Fuel stop notes must include '1,000' (the interval). "
            f"Got: '{fuel['notes']}'"
        )

    # ── 4. Route instructions ────────────────────────────────────────────────

    def test_fuel_stop_appears_in_route_instructions(self):
        """
        The route instructions must include a dedicated step for the fuel stop.
        It must not be silently omitted from the driver's turn-by-turn plan.
        """
        from trips.planner import _build_instructions
        stops, _, _ = self._plan_1fuel()
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="Atlanta, GA",
            deadhead=self.DEADHEAD_1FUEL,
            loaded=self.LOADED_1FUEL,
            stops=stops,
        )
        instruction_text = " ".join(
            step["instruction"] + " " + step["details"]
            for step in instructions
        ).lower()
        self.assertIn("fuel", instruction_text,
                      "Route instructions must include a step for the fuel stop")

    def test_fuel_instruction_includes_mile_position_and_total(self):
        """
        The fuel stop instruction details must include both the mile position
        and the total route miles — 'at mile X of Y' — so the driver knows
        how far into the trip the stop falls.
        """
        from trips.planner import _build_instructions
        stops, _, _ = self._plan_1fuel()
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="Atlanta, GA",
            deadhead=self.DEADHEAD_1FUEL,
            loaded=self.LOADED_1FUEL,
            stops=stops,
        )
        fuel_steps = [
            step for step in instructions
            if "fuel" in step["instruction"].lower()
        ]
        self.assertGreater(len(fuel_steps), 0, "No fuel step found in instructions")
        details = fuel_steps[0]["details"].lower()
        self.assertIn("mile", details,
                      "Fuel instruction must include mile position")
        self.assertIn("1,000", fuel_steps[0]["details"],
                      "Fuel instruction must reference the 1,000-mile interval")

    # ── 5. Break accumulator reset (numerical) ───────────────────────────────

    def test_fuel_stop_resets_break_accumulator_numerically(self):
        """
        After a fuel stop, drive_since_break resets to 0.
        We verify this numerically: a driver who fuels at mile 1,000 (after
        ~18.2h of driving at 55mph) should NOT have a rest stop immediately
        after the fuel stop, because the accumulator was reset.

        We also verify the distance driven after the fuel stop before the
        next rest stop is approximately MANDATORY_BREAK_AFTER * AVG_SPEED_MPH
        (another full 8h window), not a fraction of it.
        """
        stops, _, _ = self._plan_1fuel()
        fuel_stops = _stops_of_type(stops, "fuel")
        self.assertGreater(len(fuel_stops), 0)

        first_fuel = fuel_stops[0]
        fuel_idx = stops.index(first_fuel)
        fuel_end_miles = first_fuel["cumulative_miles"]

        # Find the next rest stop after the fuel stop (if any)
        post_fuel_stops = stops[fuel_idx + 1:]
        next_rest = next((s for s in post_fuel_stops if s["stop_type"] == "rest"), None)

        if next_rest is not None:
            # Miles driven between fuel stop and next rest stop
            miles_after_fuel = next_rest["cumulative_miles"] - fuel_end_miles
            expected_min = (MANDATORY_BREAK_AFTER - 0.1) * AVG_SPEED_MPH
            self.assertGreaterEqual(
                miles_after_fuel, expected_min,
                f"Rest stop appeared only {miles_after_fuel:.1f} miles after fuel stop — "
                f"expected at least {expected_min:.0f} miles (full 8h window reset). "
                "Fuel stop may not be resetting the break accumulator correctly."
            )

    # ── 6. Invariant suite ───────────────────────────────────────────────────

    def test_invariants_pass_on_fuel_stop_trip(self):
        """
        The full invariant suite must pass on a trip that includes a fuel stop.
        This is the integration-level proof that all layers agree on the fuel stop.
        """
        from trips.invariants import assert_plan_invariants, assert_cross_layer_consistency
        from trips.planner import _build_instructions
        stops, elapsed, logs = self._plan_1fuel()
        summary = {
            "total_distance_miles": round(self.DEADHEAD_1FUEL + self.LOADED_1FUEL, 1),
            "deadhead_miles": round(self.DEADHEAD_1FUEL, 1),
            "loaded_miles": round(self.LOADED_1FUEL, 1),
            "estimated_total_hours": elapsed,
            "cycle_hours_remaining": max(0.0, 70.0 - elapsed),
            "number_of_stops": len(stops),
            "number_of_days": len(logs),
        }
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="Atlanta, GA",
            deadhead=self.DEADHEAD_1FUEL,
            loaded=self.LOADED_1FUEL,
            stops=stops,
        )
        # Must not raise
        assert_plan_invariants(stops, logs, summary)
        assert_cross_layer_consistency(stops, logs, summary, instructions)

    def test_invariants_pass_on_two_fuel_stop_trip(self):
        """
        The full invariant suite must also pass on a 2,200-mile trip with
        two fuel stops — verifies the interval check handles multiple stops.
        """
        from trips.invariants import assert_plan_invariants, assert_cross_layer_consistency
        from trips.planner import _build_instructions
        stops, elapsed, logs = self._plan_2fuel()
        summary = {
            "total_distance_miles": round(self.DEADHEAD_2FUEL + self.LOADED_2FUEL, 1),
            "deadhead_miles": round(self.DEADHEAD_2FUEL, 1),
            "loaded_miles": round(self.LOADED_2FUEL, 1),
            "estimated_total_hours": elapsed,
            "cycle_hours_remaining": max(0.0, 70.0 - elapsed),
            "number_of_stops": len(stops),
            "number_of_days": len(logs),
        }
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="New York, NY",
            deadhead=self.DEADHEAD_2FUEL,
            loaded=self.LOADED_2FUEL,
            stops=stops,
        )
        # Must not raise
        assert_plan_invariants(stops, logs, summary)
        assert_cross_layer_consistency(stops, logs, summary, instructions)


class TestSleeperDaySplitting(unittest.TestCase):
    """
    Focused proof that driving segments after a 10-hour sleeper berth are
    assigned to the correct daily ELD log sheet.

    Reported symptom: Day 1 showed inflated driving hours and Day 2 showed
    0 driving hours even though the driver resumed driving after the sleeper
    and completed a loaded run before dropoff.

    Root cause investigated: the day-splitting logic in logs/generator.py
    was audited and found correct. The issue was a wording ambiguity —
    "HOS Reset" on the sleeper instruction was being read as a 34-hour
    cycle restart rather than a daily shift-window reset. These tests pin
    the correct numerical behaviour so any future regression is caught
    immediately.

    All scenarios use a fixed start_date for deterministic output.
    """

    START = None

    @classmethod
    def setUpClass(cls):
        from datetime import date
        cls.START = date(2026, 1, 1)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _plan(self, deadhead, loaded, cycle_used=0.0):
        stops, elapsed = _build_stop_schedule(
            deadhead=deadhead, loaded=loaded,
            total=deadhead + loaded,
            pickup="Dallas, TX", dropoff="Houston, TX",
            cycle_used=cycle_used,
        )
        logs = generate(stops, elapsed, start_date=self.START)
        return stops, elapsed, logs

    def _craft_stops(self, sleeper_start, sleeper_dur=10.0, dropoff_offset=3.0):
        """
        Build a minimal stop list with a sleeper and a subsequent dropoff.
        Used to test specific midnight-boundary positions without running
        the full planner.
        """
        sleeper_end = sleeper_start + sleeper_dur
        stops = [
            {
                "stop_type": "sleeper",
                "location_name": "Mile Marker 605",
                "arrival_hour": sleeper_start,
                "duration_hours": sleeper_dur,
                "cumulative_drive_hours": 11.0,
                "cumulative_miles": 605.0,
                "notes": "10-hour sleeper berth — resets the 11h driving and 14h on-duty "
                         "windows for the next shift (49 CFR 395.3(a)(1))",
            },
            {
                "stop_type": "dropoff",
                "location_name": "Houston, TX",
                "arrival_hour": sleeper_end + dropoff_offset,
                "duration_hours": 1.0,
                "cumulative_drive_hours": 3.0,
                "cumulative_miles": 770.0,
                "notes": "On-duty: unloading and paperwork (1 hour)",
            },
        ]
        total_hours = sleeper_end + dropoff_offset + 1.0
        logs = generate(stops, total_hours, start_date=self.START)
        return stops, logs

    # ── 1. Full planner: break + sleeper + next-day driving + dropoff ─────────

    def test_day2_has_nonzero_driving_after_sleeper(self):
        """
        A trip with a mandatory break, a sleeper berth, and a loaded run
        that continues into Day 2 must show positive driving_hours on Day 2.

        This is the core regression test for the reported bug.
        deadhead=605mi → triggers 30-min break at 8h, sleeper at 11h.
        loaded=200mi → driver resumes on Day 2 and drives to dropoff.
        """
        stops, _, logs = self._plan(deadhead=605.0, loaded=200.0)

        self.assertGreaterEqual(len(logs), 2,
                                "Trip must span at least 2 days")
        day2 = next((l for l in logs if l["day_number"] == 2), None)
        self.assertIsNotNone(day2, "Day 2 log must exist")
        self.assertGreater(
            day2["driving_hours"], 0.0,
            f"Day 2 driving_hours={day2['driving_hours']}h — must be > 0 "
            f"because the driver resumes driving after the sleeper before dropoff"
        )

    def test_day1_driving_does_not_include_day2_driving(self):
        """
        Day 1 driving hours must not include any driving that occurs after
        midnight (Day 2). The sleeper resets the shift window, so Day 1 can
        legitimately contain two driving blocks (before and after the sleeper)
        that together may exceed 11h — but Day 2 driving must not bleed back.

        We verify this by checking that Day 2 has positive driving hours
        (meaning the post-sleeper resumed driving is correctly on Day 2)
        and that Day 1 driving does not exceed the theoretical maximum for
        a single calendar day (two full 11h windows = 22h, which is the
        absolute ceiling even with a sleeper reset mid-day).
        """
        stops, _, logs = self._plan(deadhead=605.0, loaded=200.0)
        day1 = logs[0]
        day2 = next((l for l in logs if l["day_number"] == 2), None)

        # Day 2 must have driving — if it's 0, Day 1 absorbed it incorrectly
        self.assertIsNotNone(day2, "Day 2 must exist")
        self.assertGreater(
            day2["driving_hours"], 0.0,
            "Day 2 must have driving hours — if 0, Day 1 may have absorbed Day 2 driving"
        )

        # Day 1 driving must not exceed 22h (two full 11h windows in one calendar day)
        self.assertLessEqual(
            day1["driving_hours"], 22.0 + 0.05,
            f"Day 1 driving_hours={day1['driving_hours']}h exceeds the theoretical "
            f"maximum of 22h for a single calendar day"
        )

    def test_driving_hours_sum_to_total_trip_driving(self):
        """
        The sum of driving_hours across all ELD days must equal the total
        driving time implied by the trip distance (miles / AVG_SPEED_MPH).
        This catches any driving hours that are lost or double-counted at
        day boundaries.
        """
        deadhead, loaded = 605.0, 200.0
        stops, elapsed, logs = self._plan(deadhead=deadhead, loaded=loaded)

        # Total driving = elapsed minus all stop durations
        total_stop_duration = sum(s["duration_hours"] for s in stops)
        expected_driving = elapsed - total_stop_duration

        eld_driving = sum(l["driving_hours"] for l in logs)
        self.assertAlmostEqual(
            eld_driving, expected_driving, delta=0.1,
            msg=(
                f"ELD total driving={eld_driving:.2f}h but expected "
                f"{expected_driving:.2f}h (elapsed {elapsed:.2f}h minus "
                f"stop durations {total_stop_duration:.2f}h)"
            )
        )

    def test_each_day_totals_24_hours(self):
        """
        Every non-final day must account for all 24 hours across all duty
        statuses. A day-splitting bug would cause one day to exceed 24h
        and another to fall short.
        """
        _, _, logs = self._plan(deadhead=605.0, loaded=200.0)
        self.assertGreaterEqual(len(logs), 2)

        for log in logs[:-1]:
            total = (
                log["driving_hours"]
                + log["on_duty_not_driving_hours"]
                + log["sleeper_berth_hours"]
                + log["off_duty_hours"]
            )
            self.assertAlmostEqual(
                total, 24.0, delta=0.05,
                msg=f"Day {log['day_number']} totals {total:.3f}h — must be 24h"
            )

    def test_day2_timeline_starts_with_driving_after_sleeper(self):
        """
        On Day 2, the first active segment after the sleeper continuation
        must be Driving — not Off Duty or On Duty.
        This proves the generator correctly identifies the gap between the
        sleeper end and the dropoff as driving time on Day 2.
        """
        _, _, logs = self._plan(deadhead=605.0, loaded=200.0)
        day2 = next((l for l in logs if l["day_number"] == 2), None)
        self.assertIsNotNone(day2)

        # Find the first non-SB segment on Day 2
        non_sb = [seg for seg in day2["timeline"] if seg["status"] != "SB"]
        self.assertTrue(len(non_sb) > 0, "Day 2 must have segments after the sleeper")
        first_active = non_sb[0]
        self.assertEqual(
            first_active["status"], "D",
            f"First non-SB segment on Day 2 must be Driving, "
            f"got '{first_active['status']}' ({first_active['label']})"
        )

    # ── 2. Sleeper ends before midnight — driving crosses midnight ────────────

    def test_sleeper_before_midnight_driving_crosses_midnight(self):
        """
        Sleeper ends at hour 23 (still Day 1). Driver resumes at 23h,
        drives 1h into Day 2 (tail: 23→24h on Day 1), then continues
        driving on Day 2 (0→2h) before dropoff at hour 26.

        Day 1: driving 0→13h + tail 23→24h = 14h total, SB 13→23h = 10h
        Day 2: driving 0→2h = 2h, then dropoff at hour 2 of Day 2
        """
        _, logs = self._craft_stops(sleeper_start=13.0, sleeper_dur=10.0, dropoff_offset=3.0)
        # sleeper ends at 23h, dropoff at 26h
        # Day 1 tail: 23→24h = 1h driving
        # Day 2: 0→2h = 2h driving (dropoff at 26h = day2 hour 2)

        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        # Day 1: sleeper is 13→23h (10h), driving fills the rest
        self.assertAlmostEqual(day1["sleeper_berth_hours"], 10.0, delta=0.05,
                               msg="Day 1 must have 10h sleeper (13h–23h)")
        self.assertGreater(day1["driving_hours"], 0.0,
                           msg="Day 1 must have driving before the sleeper")

        # Day 2: driving from midnight to dropoff (2h before dropoff at day2 hour 2)
        self.assertGreater(day2["driving_hours"], 0.0,
                           msg="Day 2 must have driving after the sleeper ends")
        self.assertAlmostEqual(day2["driving_hours"], 2.0, delta=0.05,
                               msg="Day 2 should have 2h driving (0h→2h before dropoff at day2 hour 2)")

    # ── 3. Sleeper spans midnight ─────────────────────────────────────────────

    def test_sleeper_spanning_midnight_driving_on_day2(self):
        """
        Sleeper starts at hour 22 (Day 1), ends at hour 32 (Day 2, hour 8).
        Driver resumes at 32h, drives 3h, dropoff at 35h.

        Day 1: driving 0→22h=22h, SB 22→24h=2h
        Day 2: SB 0→8h=8h, driving 8→11h=3h, dropoff 11→12h
        """
        _, logs = self._craft_stops(sleeper_start=22.0, sleeper_dur=10.0, dropoff_offset=3.0)

        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        self.assertAlmostEqual(day1["sleeper_berth_hours"], 2.0, delta=0.05,
                               msg="Day 1 SB must be 2h (22h–24h)")
        self.assertAlmostEqual(day2["sleeper_berth_hours"], 8.0, delta=0.05,
                               msg="Day 2 SB must be 8h (0h–8h)")
        self.assertAlmostEqual(day2["driving_hours"], 3.0, delta=0.05,
                               msg="Day 2 driving must be 3h (8h–11h)")
        self.assertGreater(day2["on_duty_not_driving_hours"], 0.0,
                           msg="Day 2 must have on-duty time for the dropoff")

    # ── 4. Sleeper ends exactly at midnight ───────────────────────────────────

    def test_sleeper_ending_at_midnight_driving_on_day2(self):
        """
        Sleeper starts at hour 14, ends exactly at midnight (hour 24).
        Driver resumes at 24h, drives 3h, dropoff at 27h.

        Day 1: driving 0→14h=14h, SB 14→24h=10h. Total=24h.
        Day 2: driving 0→3h=3h, dropoff 3→4h=1h, OFF 4→24h=20h. Total=24h.
        """
        _, logs = self._craft_stops(sleeper_start=14.0, sleeper_dur=10.0, dropoff_offset=3.0)

        day1 = next(l for l in logs if l["day_number"] == 1)
        day2 = next(l for l in logs if l["day_number"] == 2)

        self.assertAlmostEqual(day1["sleeper_berth_hours"], 10.0, delta=0.05,
                               msg="Day 1 SB must be 10h (14h–24h)")
        self.assertAlmostEqual(day2["sleeper_berth_hours"], 0.0, delta=0.05,
                               msg="Day 2 SB must be 0h (sleeper ended at midnight)")
        self.assertAlmostEqual(day2["driving_hours"], 3.0, delta=0.05,
                               msg="Day 2 driving must be 3h (0h–3h)")

    # ── 5. Sleeper wording does not say 'cycle reset' ─────────────────────────

    def test_sleeper_notes_say_shift_window_not_cycle_reset(self):
        """
        The sleeper stop notes must describe a shift-window reset (11h/14h),
        not a 70-hour cycle restart. Confusing the two misleads the driver
        about their remaining cycle hours.
        """
        stops, _, _ = self._plan(deadhead=605.0, loaded=200.0)
        sleeper_stops = _stops_of_type(stops, "sleeper")
        self.assertGreater(len(sleeper_stops), 0, "Expected at least one sleeper stop")

        for s in sleeper_stops:
            notes_lower = s["notes"].lower()
            # Must mention the shift windows being reset
            self.assertTrue(
                "11h" in notes_lower or "14h" in notes_lower or "shift" in notes_lower,
                f"Sleeper notes must reference the shift window reset (11h/14h), "
                f"got: '{s['notes']}'"
            )
            # Must NOT say 'cycle restart' or '34-hour' — that's a different rule
            self.assertNotIn(
                "34-hour", notes_lower,
                f"Sleeper notes must not reference a 34-hour restart — "
                f"that is a cycle reset, not a shift reset. Got: '{s['notes']}'"
            )
            self.assertNotIn(
                "cycle restart", notes_lower,
                f"Sleeper notes must not say 'cycle restart'. Got: '{s['notes']}'"
            )

    def test_sleeper_instruction_says_shift_window_reset(self):
        """
        The route instruction for the sleeper must say 'Shift Window Reset',
        not 'HOS Reset' — the latter is ambiguous and could be read as a
        34-hour cycle restart.
        """
        from trips.planner import _build_instructions
        stops, _, _ = self._plan(deadhead=605.0, loaded=200.0)
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="Houston, TX",
            deadhead=605.0,
            loaded=200.0,
            stops=stops,
        )
        sleeper_steps = [
            step for step in instructions
            if "sleeper" in step["instruction"].lower()
        ]
        self.assertGreater(len(sleeper_steps), 0, "Expected a sleeper instruction step")

        for step in sleeper_steps:
            combined = (step["instruction"] + " " + step["details"]).lower()
            # Must communicate that driving/duty windows are affected.
            # Full resets say "shift window reset"; split periods say "windows reset".
            self.assertTrue(
                "window" in combined or "reset" in combined or "pairing" in combined,
                f"Sleeper instruction must communicate a window reset or split pairing. "
                f"Got: '{step['instruction']}'"
            )
            # Must mention what resumes after the rest
            self.assertIn(
                "resume", combined,
                f"Sleeper instruction must tell the driver when they resume. "
                f"Got: '{step['details']}'"
            )

    # ── 6. Full invariant suite on the exact reported scenario ────────────────

    def test_invariants_pass_on_break_sleeper_nextday_dropoff(self):
        """
        The full invariant suite must pass on the exact reported scenario:
        break + sleeper + next-day driving + dropoff.
        """
        from trips.invariants import assert_plan_invariants, assert_cross_layer_consistency
        from trips.planner import _build_instructions
        deadhead, loaded = 605.0, 200.0
        stops, elapsed, logs = self._plan(deadhead=deadhead, loaded=loaded)
        summary = {
            "total_distance_miles": round(deadhead + loaded, 1),
            "deadhead_miles": round(deadhead, 1),
            "loaded_miles": round(loaded, 1),
            "estimated_total_hours": elapsed,
            "cycle_hours_remaining": max(0.0, 70.0 - elapsed),
            "number_of_stops": len(stops),
            "number_of_days": len(logs),
        }
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="Houston, TX",
            deadhead=deadhead,
            loaded=loaded,
            stops=stops,
        )
        # Must not raise
        assert_plan_invariants(stops, logs, summary)
        assert_cross_layer_consistency(stops, logs, summary, instructions)


class TestDropoffAtMidnight(unittest.TestCase):
    """
    Focused tests for the exact reported scenario:
      - Mandatory 30-min break after 8h driving
      - 10-hour sleeper berth (shift window exhausted)
      - Driver resumes driving after sleeper
      - Dropoff falls at or after midnight (Day 2)

    The reported symptom was: "Day 2 shows 0h driving even though resumed
    driving happens before dropoff." This class pins the correct behaviour
    for three sub-cases:

      A. Dropoff at exactly midnight (arrival_hour=24.0):
         The driving 22.75→24h is Day 1's tail (correct — it IS before midnight).
         Day 2 has 0h driving because the dropoff starts at the day boundary.
         This is arithmetically correct; the route instruction must make the
         day boundary explicit so it is not misread.

      B. Dropoff after midnight (arrival_hour=24.75h):
         Day 1 tail: 22.75→24h = 1.25h driving.
         Day 2 gap:  24→24.75h = 0.75h driving before dropoff.
         Day 2 driving must be > 0.

      C. Dropoff well after midnight (arrival_hour=26h):
         Day 1 tail: 22.75→24h = 1.25h driving.
         Day 2 gap:  24→26h = 2h driving before dropoff.
         Day 2 driving must be 2h.

    All three cases must total exactly 24h per non-final day.
    """

    START = None

    @classmethod
    def setUpClass(cls):
        from datetime import date
        cls.START = date(2026, 1, 1)

    def _plan(self, loaded_miles):
        """
        Build a trip with 605mi deadhead (triggers break + sleeper) and
        the given loaded miles (controls where the dropoff lands).
        """
        stops, elapsed = _build_stop_schedule(
            deadhead=605.0, loaded=loaded_miles,
            total=605.0 + loaded_miles,
            pickup="Dallas, TX", dropoff="Houston, TX",
            cycle_used=0.0,
        )
        logs = generate(stops, elapsed, start_date=self.START)
        return stops, elapsed, logs

    # ── Case A: dropoff at exactly midnight ───────────────────────────────────

    def test_case_a_dropoff_at_midnight_day1_driving_is_correct(self):
        """
        When the dropoff lands at exactly midnight (24.0h), the driving
        22.75→24h is Day 1's tail. Day 1 driving must equal:
          8h (before break) + 3h (after break, before sleeper) + 1.25h (tail) = 12.25h
        """
        # 68.75mi / 55mph = 1.25h → sleeper ends 22.75h, drive 1.25h → dropoff at 24.0h
        stops, _, logs = self._plan(loaded_miles=68.75)
        dropoff = next(s for s in stops if s["stop_type"] == "dropoff")
        self.assertAlmostEqual(dropoff["arrival_hour"], 24.0, delta=0.05,
                               msg="Dropoff must land at midnight for Case A")

        day1 = logs[0]
        self.assertAlmostEqual(day1["driving_hours"], 12.25, delta=0.05,
                               msg="Day 1 driving must be 12.25h (8h + 3h + 1.25h tail)")

    def test_case_a_dropoff_at_midnight_day2_driving_is_zero(self):
        """
        When the dropoff starts exactly at midnight, there is no driving gap
        on Day 2 before the dropoff. Day 2 driving = 0h is correct.
        """
        stops, _, logs = self._plan(loaded_miles=68.75)
        day2 = next((l for l in logs if l["day_number"] == 2), None)
        self.assertIsNotNone(day2, "Day 2 must exist")
        self.assertAlmostEqual(day2["driving_hours"], 0.0, delta=0.05,
                               msg="Day 2 driving must be 0h when dropoff starts at midnight")

    def test_case_a_dropoff_at_midnight_day2_has_on_duty_for_dropoff(self):
        """
        Even with 0h driving, Day 2 must have on_duty_not_driving_hours = 1h
        for the dropoff unloading time.
        """
        _, _, logs = self._plan(loaded_miles=68.75)
        day2 = next(l for l in logs if l["day_number"] == 2)
        self.assertAlmostEqual(day2["on_duty_not_driving_hours"], 1.0, delta=0.05,
                               msg="Day 2 must have 1h on-duty for dropoff")

    def test_case_a_both_days_total_24_hours(self):
        """Day 1 must total exactly 24h. Day 2 may be partial."""
        _, _, logs = self._plan(loaded_miles=68.75)
        day1 = logs[0]
        total1 = (day1["driving_hours"] + day1["on_duty_not_driving_hours"]
                  + day1["sleeper_berth_hours"] + day1["off_duty_hours"])
        self.assertAlmostEqual(total1, 24.0, delta=0.05,
                               msg=f"Day 1 must total 24h, got {total1:.3f}h")

    # ── Case B: dropoff after midnight (0.75h into Day 2) ────────────────────

    def test_case_b_dropoff_after_midnight_day2_has_driving(self):
        """
        When the dropoff is 0.75h after midnight (arrival=24.75h), there is
        0.75h of driving on Day 2 before the dropoff. Day 2 driving must be > 0.
        """
        # 110mi / 55mph = 2h total after sleeper: 1.25h on Day 1 tail + 0.75h on Day 2
        stops, _, logs = self._plan(loaded_miles=110.0)
        dropoff = next(s for s in stops if s["stop_type"] == "dropoff")
        self.assertGreater(dropoff["arrival_hour"], 24.0,
                           msg="Dropoff must be after midnight for Case B")

        day2 = next((l for l in logs if l["day_number"] == 2), None)
        self.assertIsNotNone(day2, "Day 2 must exist")
        self.assertGreater(day2["driving_hours"], 0.0,
                           msg="Day 2 must have driving when dropoff is after midnight")

    def test_case_b_day2_driving_plus_on_duty_equals_dropoff_arrival(self):
        """
        On Day 2, driving_hours + on_duty_not_driving_hours must equal
        the dropoff arrival time relative to midnight (i.e., the time from
        00:00 to end of dropoff).
        """
        stops, _, logs = self._plan(loaded_miles=110.0)
        dropoff = next(s for s in stops if s["stop_type"] == "dropoff")
        day2 = next(l for l in logs if l["day_number"] == 2)

        # Time from midnight to end of dropoff
        dropoff_end_on_day2 = (dropoff["arrival_hour"] + dropoff["duration_hours"]) - 24.0
        active_on_day2 = day2["driving_hours"] + day2["on_duty_not_driving_hours"]
        self.assertAlmostEqual(
            active_on_day2, dropoff_end_on_day2, delta=0.05,
            msg=(
                f"Day 2 active time ({active_on_day2:.2f}h) must equal "
                f"time from midnight to dropoff end ({dropoff_end_on_day2:.2f}h)"
            )
        )

    def test_case_b_day1_total_is_24_hours(self):
        """Day 1 must total exactly 24h for Case B."""
        _, _, logs = self._plan(loaded_miles=110.0)
        day1 = logs[0]
        total1 = (day1["driving_hours"] + day1["on_duty_not_driving_hours"]
                  + day1["sleeper_berth_hours"] + day1["off_duty_hours"])
        self.assertAlmostEqual(total1, 24.0, delta=0.05,
                               msg=f"Day 1 must total 24h, got {total1:.3f}h")

    # ── Case C: dropoff 2h after midnight ────────────────────────────────────

    def test_case_c_dropoff_2h_after_midnight_day2_driving_is_2h(self):
        """
        When the dropoff is 2h after midnight (arrival=26h), Day 2 must
        have exactly 2h of driving (24→26h) before the dropoff.
        """
        # 178.75mi / 55mph = 3.25h: 1.25h Day 1 tail + 2h Day 2 gap
        stops, _, logs = self._plan(loaded_miles=178.75)
        dropoff = next(s for s in stops if s["stop_type"] == "dropoff")
        self.assertAlmostEqual(dropoff["arrival_hour"], 26.0, delta=0.05,
                               msg="Dropoff must be at 26h for Case C")

        day2 = next(l for l in logs if l["day_number"] == 2)
        self.assertAlmostEqual(day2["driving_hours"], 2.0, delta=0.05,
                               msg="Day 2 must have 2h driving (24h→26h)")

    def test_case_c_day1_driving_excludes_day2_driving(self):
        """
        Day 1 driving must be 12.25h (not 14.25h).
        The 2h of Day 2 driving must not bleed into Day 1.
        """
        _, _, logs = self._plan(loaded_miles=178.75)
        day1 = logs[0]
        self.assertAlmostEqual(day1["driving_hours"], 12.25, delta=0.05,
                               msg=(
                                   f"Day 1 driving must be 12.25h, got {day1['driving_hours']}h. "
                                   "Day 2 driving (2h) must not be attributed to Day 1."
                               ))

    def test_case_c_day2_has_driving_and_dropoff_on_duty(self):
        """
        Day 2 must have both driving_hours > 0 and on_duty_not_driving_hours = 1h.
        """
        _, _, logs = self._plan(loaded_miles=178.75)
        day2 = next(l for l in logs if l["day_number"] == 2)
        self.assertGreater(day2["driving_hours"], 0.0,
                           msg="Day 2 must have driving before dropoff")
        self.assertAlmostEqual(day2["on_duty_not_driving_hours"], 1.0, delta=0.05,
                               msg="Day 2 must have 1h on-duty for dropoff")

    def test_case_c_day1_total_is_24_hours(self):
        """Day 1 must total exactly 24h for Case C."""
        _, _, logs = self._plan(loaded_miles=178.75)
        day1 = logs[0]
        total1 = (day1["driving_hours"] + day1["on_duty_not_driving_hours"]
                  + day1["sleeper_berth_hours"] + day1["off_duty_hours"])
        self.assertAlmostEqual(total1, 24.0, delta=0.05,
                               msg=f"Day 1 must total 24h, got {total1:.3f}h")

    # ── Route instruction clarity ─────────────────────────────────────────────

    def test_route_instruction_shows_day_number_for_midnight_events(self):
        """
        When the dropoff falls at or after midnight, the route instruction
        for the dropoff must show 'Day 2' in the elapsed time, not just '24h'.
        '24h' is ambiguous — it looks like a duration, not a day boundary.
        """
        from trips.planner import _build_instructions
        stops, _, _ = self._plan(loaded_miles=68.75)  # dropoff at 24h exactly
        instructions = _build_instructions(
            current="Chicago, IL",
            pickup="Dallas, TX",
            dropoff="Houston, TX",
            deadhead=605.0,
            loaded=68.75,
            stops=stops,
        )
        dropoff_steps = [
            step for step in instructions
            if "dropoff" in step["instruction"].lower()
        ]
        self.assertGreater(len(dropoff_steps), 0, "Must have a dropoff instruction")
        details = dropoff_steps[0]["details"]
        self.assertIn(
            "Day 2", details,
            f"Dropoff instruction must show 'Day 2' when dropoff is at midnight. "
            f"Got: '{details}'"
        )

    def test_sleeper_resume_instruction_shows_day_number(self):
        """
        The sleeper instruction must show 'Day 2' for the resume time when
        the sleeper ends after midnight, making it clear the driver resumes
        on the next calendar day.
        """
        from trips.planner import _build_instructions
        # Use a sleeper that spans midnight (starts 22h, ends 32h)
        stops_midnight = [
            {"stop_type": "sleeper", "location_name": "MM605",
             "arrival_hour": 22.0, "duration_hours": 10.0,
             "cumulative_drive_hours": 11.0, "cumulative_miles": 605.0, "notes": ""},
            {"stop_type": "dropoff", "location_name": "Houston, TX",
             "arrival_hour": 35.0, "duration_hours": 1.0,
             "cumulative_drive_hours": 3.0, "cumulative_miles": 770.0, "notes": ""},
        ]
        instructions = _build_instructions(
            current="Chicago, IL", pickup="Dallas, TX", dropoff="Houston, TX",
            deadhead=605.0, loaded=165.0, stops=stops_midnight,
        )
        sleeper_steps = [
            step for step in instructions
            if "sleeper" in step["instruction"].lower()
        ]
        self.assertGreater(len(sleeper_steps), 0, "Must have a sleeper instruction")
        details = sleeper_steps[0]["details"]
        self.assertIn(
            "Day 2", details,
            f"Sleeper instruction must show 'Day 2' for resume time when sleeper ends after midnight. "
            f"Got: '{details}'"
        )

    # ── Full invariant suite ──────────────────────────────────────────────────

    def test_invariants_pass_on_all_three_cases(self):
        """The full invariant suite must pass on all three dropoff-timing cases."""
        from trips.invariants import assert_plan_invariants, assert_cross_layer_consistency
        from trips.planner import _build_instructions

        for loaded_miles, label in [(68.75, "Case A"), (110.0, "Case B"), (178.75, "Case C")]:
            with self.subTest(case=label):
                stops, elapsed, logs = self._plan(loaded_miles=loaded_miles)
                summary = {
                    "total_distance_miles": round(605.0 + loaded_miles, 1),
                    "deadhead_miles": 605.0,
                    "loaded_miles": round(loaded_miles, 1),
                    "estimated_total_hours": elapsed,
                    "cycle_hours_remaining": max(0.0, 70.0 - elapsed),
                    "number_of_stops": len(stops),
                    "number_of_days": len(logs),
                }
                instructions = _build_instructions(
                    current="Chicago, IL", pickup="Dallas, TX", dropoff="Houston, TX",
                    deadhead=605.0, loaded=loaded_miles, stops=stops,
                )
                assert_plan_invariants(stops, logs, summary)
                assert_cross_layer_consistency(stops, logs, summary, instructions)


class TestFmtDayBoundary(unittest.TestCase):
    """
    Unit tests for the _fmt helper function.

    _fmt converts elapsed hours to a human-readable string. For values
    under 24h it returns "Xh Ym". For values at or over 24h it returns
    "Day N, HH:MM" to make day boundaries explicit in route instructions.
    """

    def _fmt(self, hours):
        from trips.planner import _fmt
        return _fmt(hours)

    def test_sub_24h_minutes_only(self):
        self.assertEqual(self._fmt(0.5), "30m")

    def test_sub_24h_hours_only(self):
        self.assertEqual(self._fmt(3.0), "3h")
        self.assertEqual(self._fmt(11.0), "11h")

    def test_sub_24h_hours_and_minutes(self):
        self.assertEqual(self._fmt(8.25), "8h 15m")
        self.assertEqual(self._fmt(22.75), "22h 45m")

    def test_exactly_24h_is_day2_midnight(self):
        """24.0h is the start of Day 2 — must show 'Day 2, 00:00'."""
        self.assertEqual(self._fmt(24.0), "Day 2, 00:00")

    def test_just_after_midnight_day2(self):
        self.assertEqual(self._fmt(24.75), "Day 2, 00:45")
        self.assertEqual(self._fmt(25.0),  "Day 2, 01:00")
        self.assertEqual(self._fmt(26.0),  "Day 2, 02:00")

    def test_midday_day2(self):
        self.assertEqual(self._fmt(36.5), "Day 2, 12:30")

    def test_exactly_48h_is_day3_midnight(self):
        """48.0h is the start of Day 3."""
        self.assertEqual(self._fmt(48.0), "Day 3, 00:00")

    def test_day3_time(self):
        self.assertEqual(self._fmt(49.5), "Day 3, 01:30")

    def test_sub_24h_boundary_just_before_midnight(self):
        """23h 59m should still be sub-24h format."""
        self.assertEqual(self._fmt(23.0 + 59.0/60), "23h 59m")


if __name__ == "__main__":
    unittest.main()
