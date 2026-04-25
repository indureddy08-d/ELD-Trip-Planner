from django.contrib import admin
from .models import ELDLog


@admin.register(ELDLog)
class ELDLogAdmin(admin.ModelAdmin):
    list_display = ("trip", "day_number", "log_date", "driving_hours",
                    "on_duty_not_driving_hours", "sleeper_berth_hours", "total_miles")
    list_filter = ("log_date",)
    search_fields = ("trip__pickup_location", "trip__dropoff_location")
    readonly_fields = ("timeline",)
