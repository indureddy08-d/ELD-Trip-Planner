"""
FMCSA Hours of Service — Property-Carrying Driver
70-hour / 8-day cycle. No adverse driving conditions.

All constants live here. Nothing else in the codebase hardcodes
these values — they import from this module.
"""

# ── Driving limits ────────────────────────────────────────────────────────────
MAX_DRIVING_PER_SHIFT: float = 11.0       # 11-hour driving rule
MAX_ON_DUTY_PER_SHIFT: float = 14.0       # 14-hour on-duty window
REQUIRED_OFF_DUTY: float = 10.0           # Consecutive hours off to reset shift

# ── Cycle ─────────────────────────────────────────────────────────────────────
CYCLE_LIMIT: float = 70.0                 # 70 hours in any 8 consecutive days

# ── Mandatory break ───────────────────────────────────────────────────────────
MANDATORY_BREAK_AFTER: float = 8.0        # 30-min break required after 8h driving
MANDATORY_BREAK_DURATION: float = 0.5     # 30 minutes

# ── Split sleeper berth provision (49 CFR 395.1(g)) ──────────────────────────
# A driver may split the required 10h off-duty into two periods:
#   - One period of at least 8 consecutive hours in the sleeper berth
#   - One period of at least 2 hours (sleeper berth or off-duty)
# When paired, neither period counts against the 14-hour driving window.
# The planner uses the simpler 8+2 split (most common in practice).
SPLIT_SB_LONG: float = 8.0               # Minimum long sleeper berth period
SPLIT_SB_SHORT: float = 2.0              # Minimum short off-duty/SB period

# ── Operational assumptions ───────────────────────────────────────────────────
FUEL_INTERVAL_MILES: float = 1000.0       # Fuel stop at least every 1000 miles
PICKUP_DURATION: float = 1.0              # 1 hour on-duty for loading
DROPOFF_DURATION: float = 1.0             # 1 hour on-duty for unloading
AVG_SPEED_MPH: float = 55.0              # Conservative highway average
FUEL_STOP_DURATION: float = 0.5          # 30 minutes per fuel stop
PRE_TRIP_DURATION: float = 0.25          # 15 minutes on-duty for pre-trip inspection
