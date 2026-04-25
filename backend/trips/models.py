from django.db import models


class Trip(models.Model):
    """
    Represents a single planned trip.
    Stores the raw inputs and the computed summary so we can
    retrieve a trip later without re-running the planner.
    """
    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used_hours = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    # FMCSA RODS header fields (49 CFR 395.8)
    driver_name = models.CharField(max_length=255, blank=True, default="")
    carrier_name = models.CharField(max_length=255, blank=True, default="")
    main_office_address = models.CharField(max_length=255, blank=True, default="")
    vehicle_numbers = models.CharField(max_length=255, blank=True, default="")
    co_driver_name = models.CharField(max_length=255, blank=True, default="")
    shipper_and_commodity = models.CharField(max_length=255, blank=True, default="")

    # Computed at plan time — stored for fast retrieval
    total_distance_miles = models.FloatField(null=True, blank=True)
    estimated_total_hours = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Trip"
        verbose_name_plural = "Trips"

    def __str__(self):
        return f"{self.pickup_location} → {self.dropoff_location}"


class TripStop(models.Model):
    """
    An individual stop on a trip — pickup, dropoff, rest, sleeper, or fuel.
    Ordered by arrival_hour so the timeline is always correct.
    """
    STOP_TYPES = [
        ("pre_trip", "Pre-Trip Inspection"),
        ("pickup",   "Pickup"),
        ("dropoff",  "Dropoff"),
        ("rest",     "30-Min Off-Duty Break"),
        ("sleeper",  "10-Hour Sleeper Berth"),
        ("fuel",     "Fuel Stop"),
    ]

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stops")
    stop_type = models.CharField(max_length=20, choices=STOP_TYPES)
    location_name = models.CharField(max_length=255)
    arrival_hour = models.FloatField(help_text="Hours elapsed from trip start")
    duration_hours = models.FloatField()
    cumulative_drive_hours = models.FloatField()
    cumulative_miles = models.FloatField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["arrival_hour"]
        verbose_name = "Trip Stop"
        verbose_name_plural = "Trip Stops"

    def __str__(self):
        return f"{self.get_stop_type_display()} @ {self.location_name}"
