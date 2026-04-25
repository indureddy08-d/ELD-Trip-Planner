"""
RoutingService — the only entry point for route resolution.

Responsibilities:
  1. Select the configured provider (ORS or fallback)
  2. Call the provider
  3. If the live provider fails, transparently fall back and log a warning
  4. Return a normalised RouteResult

Nothing outside this module needs to know which provider is active.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from django.conf import settings

from .providers.base import BaseRouteProvider, RouteResult, RouteProviderError
from .providers.fallback import FallbackProvider

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _build_provider() -> BaseRouteProvider:
    """
    Instantiate the configured provider once per process.
    lru_cache ensures we don't re-read settings on every request.
    """
    api_key = getattr(settings, "ORS_API_KEY", None)

    if api_key:
        # Import lazily so the ORS dependency is only loaded when needed
        from .providers.openrouteservice import OpenRouteServiceProvider
        logger.info("Routing: using OpenRouteService provider")
        return OpenRouteServiceProvider(api_key=api_key)

    logger.warning(
        "Routing: ORS_API_KEY not set — using fallback lookup table. "
        "Set ORS_API_KEY in .env for live routing data."
    )
    return FallbackProvider()


class RoutingService:
    """
    Stateless service. Instantiate per-request or use the module-level
    `get_route()` convenience function.
    """

    def __init__(self) -> None:
        self._primary = _build_provider()
        self._fallback = FallbackProvider()

    def get_route(
        self,
        origin: str,
        waypoints: list[str] | None = None,
        destination: str = "",
    ) -> RouteResult:
        """
        Resolve a route. Falls back to the lookup table if the primary
        provider raises RouteProviderError.
        """
        wps = waypoints or []

        try:
            result = self._primary.get_route(origin, wps, destination)
            return result
        except RouteProviderError as exc:
            logger.warning(
                "Primary routing provider failed (%s). Falling back to lookup table. Error: %s",
                type(self._primary).__name__, exc,
            )
            return self._fallback.get_route(origin, wps, destination)


# ── Module-level convenience ──────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_service() -> RoutingService:
    """
    Return the process-level RoutingService singleton.
    lru_cache is thread-safe — safe for both WSGI and threaded servers.
    """
    return RoutingService()


def get_route(origin: str, waypoints: list[str] | None = None, destination: str = "") -> RouteResult:
    """
    Module-level shortcut. Returns a cached RoutingService and resolves the route.
    Use this in views and the trip planner — don't instantiate RoutingService directly.
    """
    return _get_service().get_route(origin, waypoints or [], destination)
