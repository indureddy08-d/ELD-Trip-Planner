import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteRequestSerializer, RouteResultSerializer
from .service import get_route
from .providers.base import RouteProviderError

logger = logging.getLogger(__name__)


class RouteView(APIView):
    """
    POST /api/route/

    Resolves a three-point route (current → pickup → dropoff) and returns
    distance, estimated driving time, per-leg breakdown, and coordinates
    for map display.

    This endpoint is intentionally decoupled from trip planning — it can
    be called independently to preview a route before committing to a plan.
    """

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "bad_request", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        try:
            result = get_route(
                origin=data["current_location"],
                waypoints=[data["pickup_location"]],
                destination=data["dropoff_location"],
            )
        except RouteProviderError as exc:
            logger.error("Route resolution failed: %s", exc)
            return Response(
                {"error": "routing_failed", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception("Unexpected error in RouteView")
            return Response(
                {"error": "internal_server_error", "detail": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            RouteResultSerializer(result).data,
            status=status.HTTP_200_OK,
        )
