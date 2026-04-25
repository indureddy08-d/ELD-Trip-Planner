"""
Abstract base class for route providers.

Any provider — OpenRouteService, Google Maps, HERE, MapBox — must
implement this interface. The rest of the codebase only ever talks
to this contract, so swapping providers is a one-line config change.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Coordinate:
    lat: float
    lng: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.lat, self.lng)


@dataclass
class RouteLeg:
    """One segment of a multi-leg route (e.g. origin → pickup, pickup → dropoff)."""
    from_label: str
    to_label: str
    distance_miles: float
    duration_hours: float
    coordinates: list[Coordinate] = field(default_factory=list)


@dataclass
class RouteResult:
    """Normalised output returned by every provider."""
    total_distance_miles: float
    total_duration_hours: float
    legs: list[RouteLeg]
    provider: str                        # which provider produced this result
    from_cache: bool = False             # came from the fallback lookup table


class RouteProviderError(Exception):
    """Raised when a provider cannot fulfil the request."""


class BaseRouteProvider(ABC):

    @abstractmethod
    def get_route(
        self,
        origin: str,
        waypoints: list[str],
        destination: str,
    ) -> RouteResult:
        """
        Resolve a route from origin through optional waypoints to destination.

        Args:
            origin:      Plain-text location string (e.g. "Chicago, IL")
            waypoints:   Intermediate stops in order (may be empty)
            destination: Plain-text destination string

        Returns:
            RouteResult with normalised distance, duration, legs, and coordinates.

        Raises:
            RouteProviderError: on any unrecoverable provider failure.
        """
