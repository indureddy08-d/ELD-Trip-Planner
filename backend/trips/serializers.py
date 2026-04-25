from rest_framework import serializers
from .models import Trip, TripStop
from logs.serializers import ELDLogSerializer


class TripRequestSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=255, trim_whitespace=True)
    pickup_location  = serializers.CharField(max_length=255, trim_whitespace=True)
    dropoff_location = serializers.CharField(max_length=255, trim_whitespace=True)
    # Accept 0–70. Values at 70 are structurally valid inputs — the planner
    # enforces the compliance rule and returns a 422 with a clear message.
    current_cycle_used_hours = serializers.FloatField(
        min_value=0,
        max_value=70,
        error_messages={
            "min_value": "Cycle hours cannot be negative. Enter a value between 0 and 70.",
            "max_value": "Cycle hours cannot exceed 70. Enter a value between 0 and 70.",
            "invalid":   "Enter a valid number for cycle hours used (e.g. 24 or 36.5).",
        },
    )

    # FMCSA RODS header fields (49 CFR 395.8) — all optional so existing
    # integrations don't break, but rendered on the ELD log sheet when provided.
    driver_name            = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", trim_whitespace=True)
    carrier_name           = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", trim_whitespace=True)
    main_office_address    = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", trim_whitespace=True)
    vehicle_numbers        = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", trim_whitespace=True)
    co_driver_name         = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", trim_whitespace=True)
    shipper_and_commodity  = serializers.CharField(max_length=255, required=False, allow_blank=True, default="", trim_whitespace=True)

    def validate(self, data):
        if data["pickup_location"].lower() == data["dropoff_location"].lower():
            raise serializers.ValidationError(
                {"dropoff_location": "Pickup and dropoff cannot be the same location."}
            )
        return data


class NoticeSerializer(serializers.Serializer):
    """Shared shape for both warnings and assumptions."""
    code    = serializers.CharField()
    message = serializers.CharField()


class TripStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripStop
        fields = [
            "id", "stop_type", "location_name", "arrival_hour",
            "duration_hours", "cumulative_drive_hours", "cumulative_miles", "notes",
        ]


class TripSerializer(serializers.ModelSerializer):
    stops    = TripStopSerializer(many=True, read_only=True)
    eld_logs = ELDLogSerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = [
            "id", "current_location", "pickup_location", "dropoff_location",
            "current_cycle_used_hours", "total_distance_miles",
            "estimated_total_hours", "created_at",
            # FMCSA RODS header fields
            "driver_name", "carrier_name", "main_office_address",
            "vehicle_numbers", "co_driver_name", "shipper_and_commodity",
            "stops", "eld_logs",
        ]
