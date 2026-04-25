"""
OpenRouteService provider.

Free tier: 2,000 requests/day, no credit card required.
Sign up at https://openrouteservice.org/dev/#/signup to get an API key.

Docs: https://openrouteservice.org/dev/#/api-docs/geocode/search/get
      https://openrouteservice.org/dev/#/api-docs/v2/directions/{profile}/get
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from .base import (
    BaseRouteProvider, Coordinate, RouteLeg, RouteResult, RouteProviderError,
)

logger = logging.getLogger(__name__)

_GEOCODE_URL   = "https://api.openrouteservice.org/geocode/search"
_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv"  # HGV = heavy goods vehicle
_METERS_PER_MILE = 1609.344
_SECONDS_PER_HOUR = 3600.0
_REQUEST_TIMEOUT = 10  # seconds — never block the request thread indefinitely


class OpenRouteServiceProvider(BaseRouteProvider):
    """
    Wraps the OpenRouteService Directions + Geocoding APIs.

    The client is intentionally thin — it only handles HTTP, auth headers,
    and response parsing. All business decisions live in RoutingService.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("OpenRouteService API key is required.")
        self._api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ── Public interface ──────────────────────────────────────────────────────

    def get_route(
        self,
        origin: str,
        waypoints: list[str],
        destination: str,
    ) -> RouteResult:
        all_locations = [origin] + waypoints + [destination]
        coordinates = [self._geocode(loc) for loc in all_locations]
        return self._directions(all_locations, coordinates)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _geocode(self, location: str) -> list[float]:
        """Resolve a plain-text location to [lng, lat] for the ORS API."""
        try:
            resp = self._session.get(
                _GEOCODE_URL,
                params={"text": location, "size": 1},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.Timeout:
            raise RouteProviderError(f"Geocoding timed out for '{location}'.")
        except requests.RequestException as exc:
            raise RouteProviderError(f"Geocoding failed for '{location}': {exc}") from exc

        data = resp.json()
        features = data.get("features", [])
        if not features:
            raise RouteProviderError(
                f"Could not geocode '{location}'. "
                "Try a more specific address (e.g. 'Chicago, IL, USA')."
            )

        # ORS returns [lng, lat]
        return features[0]["geometry"]["coordinates"]

    def _directions(
        self,
        labels: list[str],
        coordinates: list[list[float]],
    ) -> RouteResult:
        """Call the ORS Directions API and parse the response into RouteResult."""
        payload: dict[str, Any] = {
            "coordinates": coordinates,
            "instructions": True,   # required — ORS omits segments[] when False
            "geometry": True,
            "units": "mi",
            "geometry_simplify": False,
        }

        try:
            resp = self._session.post(
                _DIRECTIONS_URL,
                json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.Timeout:
            raise RouteProviderError("Directions request timed out.")
        except requests.HTTPError as exc:
            try:
                detail = exc.response.json().get("error", {}).get("message", str(exc))
            except Exception:
                detail = str(exc)
            raise RouteProviderError(f"Directions API error: {detail}") from exc
        except requests.RequestException as exc:
            raise RouteProviderError(f"Directions request failed: {exc}") from exc

        return self._parse_directions(resp.json(), labels, coordinates)

    def _parse_directions(
        self,
        data: dict,
        labels: list[str],
        raw_coords: list[list[float]],
    ) -> RouteResult:
        routes = data.get("routes", [])
        if not routes:
            raise RouteProviderError("ORS returned no routes for this request.")

        route = routes[0]
        summary = route["summary"]

        total_miles = summary["distance"]
        total_hours = summary["duration"] / _SECONDS_PER_HOUR

        # Decode the full route geometry (ORS returns encoded polyline by default)
        all_coords: list[Coordinate] = []
        geometry = route.get("geometry")
        if isinstance(geometry, str):
            all_coords = _decode_polyline(geometry)
        elif isinstance(geometry, dict):
            all_coords = [
                Coordinate(lat=c[1], lng=c[0])
                for c in geometry.get("coordinates", [])
            ]

        # Build per-leg breakdown using way_points indices into all_coords
        legs: list[RouteLeg] = []
        ors_segments = route.get("segments", [])
        way_points = route.get("way_points", [])  # e.g. [0, 142, 387] — indices into all_coords

        for i, seg in enumerate(ors_segments):
            from_label = labels[i] if i < len(labels) else f"Waypoint {i}"
            to_label   = labels[i + 1] if (i + 1) < len(labels) else labels[-1]

            leg_miles = seg["distance"]
            leg_hours = seg["duration"] / _SECONDS_PER_HOUR

            # Slice the coordinates that belong to this leg
            leg_coords: list[Coordinate] = []
            if all_coords and len(way_points) >= i + 2:
                start_idx = way_points[i]
                end_idx   = way_points[i + 1] + 1
                leg_coords = all_coords[start_idx:end_idx]

            legs.append(RouteLeg(
                from_label=from_label,
                to_label=to_label,
                distance_miles=round(leg_miles, 1),
                duration_hours=round(leg_hours, 3),
                coordinates=leg_coords,
            ))

        return RouteResult(
            total_distance_miles=round(total_miles, 1),
            total_duration_hours=round(total_hours, 3),
            legs=legs,
            provider="openrouteservice",
        )


# ── Encoded polyline decoder ──────────────────────────────────────────────────

def _decode_polyline(encoded: str) -> list[Coordinate]:
    """
    Decode a Google-style encoded polyline string into a list of Coordinates.
    ORS uses precision=5 (the standard) by default.
    """
    coords: list[Coordinate] = []
    index = 0
    length = len(encoded)
    lat = 0
    lng = 0

    while index < length:
        # Decode latitude
        result, shift = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        # Decode longitude
        result, shift = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coords.append(Coordinate(lat=lat / 1e5, lng=lng / 1e5))

    return coords
