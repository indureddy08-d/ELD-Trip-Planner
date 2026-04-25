from django.db import models


class ELDLog(models.Model):
    """
    One ELD log sheet per calendar day of a trip.
    Stores both the hour totals and the full 24-hour duty timeline
    so the frontend can render the grid without recalculating anything.
    """
    trip = models.ForeignKey(
        "trips.Trip",
        on_delete=models.CASCADE,
        related_name="eld_logs",
    )
    log_date = models.DateField()
    day_number = models.PositiveSmallIntegerField()

    # Hour totals — must sum to ≤ 24
    off_duty_hours = models.FloatField(default=0)
    sleeper_berth_hours = models.FloatField(default=0)
    driving_hours = models.FloatField(default=0)
    on_duty_not_driving_hours = models.FloatField(default=0)

    # Full timeline: [{status, label, start, end}, ...]
    # start/end are hours within the 24-hour day (0–24)
    timeline = models.JSONField(default=list)

    total_miles = models.FloatField(default=0)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["day_number"]
        verbose_name = "ELD Log"
        verbose_name_plural = "ELD Logs"

    def __str__(self):
        return f"Day {self.day_number} — {self.log_date}"
