import logging

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Trip, TripStop
from .serializers import TripRequestSerializer, TripSerializer
from .planner import plan
from logs.models import ELDLog

logger = logging.getLogger(__name__)


@api_view(["GET"])
def health_check(request):
    return Response({"status": "ok", "message": "ELD Trip Planner API is running"})


class PlanTripView(APIView):
    """
    POST /api/trips/plan/

    Accepts trip inputs, runs the HOS planning engine, persists the
    full result, and returns it in a single response.
    """

    def post(self, request):
        serializer = TripRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "bad_request", "detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        try:
            result = plan(
                current_location=data["current_location"],
                pickup_location=data["pickup_location"],
                dropoff_location=data["dropoff_location"],
                cycle_used=data["current_cycle_used_hours"],
            )
        except ValueError as exc:
            logger.warning("HOS planning rejected: %s", exc)
            return Response(
                {"error": "unprocessable_entity", "detail": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception:
            logger.exception("Unexpected error during trip planning")
            return Response(
                {"error": "internal_server_error", "detail": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        trip = self._persist(data, result)

        return Response(
            {
                "trip_id": trip.id,
                "summary": result["summary"],
                "stops": result["stops"],
                "route_instructions": result["route_instructions"],
                "eld_logs": result["eld_logs"],
                "warnings": result["warnings"],
                "assumptions": result["assumptions"],
                # FMCSA RODS header fields — echoed back so the frontend
                # can render them on the ELD log sheet without a second request.
                "driver_info": {
                    "driver_name":           data.get("driver_name", ""),
                    "carrier_name":          data.get("carrier_name", ""),
                    "main_office_address":   data.get("main_office_address", ""),
                    "vehicle_numbers":       data.get("vehicle_numbers", ""),
                    "co_driver_name":        data.get("co_driver_name", ""),
                    "shipper_and_commodity": data.get("shipper_and_commodity", ""),
                },
            },
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _persist(data: dict, result: dict) -> Trip:
        # Wrap all three writes in a single transaction. If TripStop or
        # ELDLog bulk_create fails, the Trip row is rolled back too —
        # no orphaned records.
        with transaction.atomic():
            trip = Trip.objects.create(
                current_location=data["current_location"],
                pickup_location=data["pickup_location"],
                dropoff_location=data["dropoff_location"],
                current_cycle_used_hours=data["current_cycle_used_hours"],
                total_distance_miles=result["summary"]["total_distance_miles"],
                estimated_total_hours=result["summary"]["estimated_total_hours"],
                # FMCSA RODS header fields
                driver_name=data.get("driver_name", ""),
                carrier_name=data.get("carrier_name", ""),
                main_office_address=data.get("main_office_address", ""),
                vehicle_numbers=data.get("vehicle_numbers", ""),
                co_driver_name=data.get("co_driver_name", ""),
                shipper_and_commodity=data.get("shipper_and_commodity", ""),
            )
            TripStop.objects.bulk_create([
                TripStop(trip=trip, **stop) for stop in result["stops"]
            ])
            ELDLog.objects.bulk_create([
                ELDLog(
                    trip=trip,
                    log_date=log["log_date"],
                    day_number=log["day_number"],
                    driving_hours=log["driving_hours"],
                    on_duty_not_driving_hours=log["on_duty_not_driving_hours"],
                    sleeper_berth_hours=log["sleeper_berth_hours"],
                    off_duty_hours=log["off_duty_hours"],
                    total_miles=log["total_miles"],
                    timeline=log["timeline"],
                    remarks=log["remarks"],
                )
                for log in result["eld_logs"]
            ])
        return trip


class TripDetailView(APIView):
    """GET /api/trips/<id>/"""

    def get(self, request, trip_id):
        try:
            trip = Trip.objects.prefetch_related("stops", "eld_logs").get(pk=trip_id)
        except Trip.DoesNotExist:
            return Response(
                {"error": "not_found", "detail": "Trip not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(TripSerializer(trip).data)


class TripListView(APIView):
    """GET /api/trips/"""

    def get(self, request):
        trips = Trip.objects.prefetch_related("stops", "eld_logs").all()[:20]
        return Response(TripSerializer(trips, many=True).data)
