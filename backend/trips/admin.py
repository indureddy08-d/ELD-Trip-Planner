from django.contrib import admin
from .models import Trip, TripStop


class TripStopInline(admin.TabularInline):
    model = TripStop
    extra = 0
    readonly_fields = ("stop_type", "location_name", "arrival_hour",
                       "duration_hours", "cumulative_miles", "notes")
    can_delete = False


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ("id", "current_location", "pickup_location", "dropoff_location",
                    "total_distance_miles", "estimated_total_hours", "created_at")
    list_filter = ("created_at",)
    search_fields = ("current_location", "pickup_location", "dropoff_location")
    readonly_fields = ("total_distance_miles", "estimated_total_hours", "created_at")
    inlines = [TripStopInline]


@admin.register(TripStop)
class TripStopAdmin(admin.ModelAdmin):
    list_display = ("trip", "stop_type", "location_name", "arrival_hour", "cumulative_miles")
    list_filter = ("stop_type",)
