"""
Fallback provider — uses the static distance lookup table.

Used when:
  - No API key is configured (local dev without a key)
  - The live provider fails (network error, quota exceeded, etc.)

Returns no coordinates or legs — just distance and estimated duration.
The HOS planner works fine with just those two values.
"""
from __future__ import annotations

import logging

from .base import BaseRouteProvider, RouteLeg, RouteResult, RouteProviderError
from routing.distance import get_distance
from compliance.hos_rules import AVG_SPEED_MPH

logger = logging.getLogger(__name__)


class FallbackProvider(BaseRouteProvider):

    def get_route(
        self,
        origin: str,
        waypoints: list[str],
        destination: str,
    ) -> RouteResult:
        all_stops = [origin] + waypoints + [destination]
        legs: list[RouteLeg] = []
        total_miles = 0.0

        for i in range(len(all_stops) - 1):
            frm = all_stops[i]
            to  = all_stops[i + 1]
            miles = get_distance(frm, to)
            hours = miles / AVG_SPEED_MPH

            legs.append(RouteLeg(
                from_label=frm,
                to_label=to,
                distance_miles=round(miles, 1),
                duration_hours=round(hours, 3),
                coordinates=[],
            ))
            total_miles += miles

        total_hours = total_miles / AVG_SPEED_MPH

        logger.info(
            "FallbackProvider used for route %s → %s (%.0f mi)",
            origin, destination, total_miles,
        )

        return RouteResult(
            total_distance_miles=round(total_miles, 1),
            total_duration_hours=round(total_hours, 3),
            legs=legs,
            provider="fallback_lookup",
            from_cache=True,
        )
