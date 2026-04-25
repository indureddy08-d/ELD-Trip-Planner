from rest_framework import serializers
from .models import ELDLog


class ELDLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ELDLog
        fields = [
            "id", "log_date", "day_number",
            "driving_hours", "on_duty_not_driving_hours",
            "sleeper_berth_hours", "off_duty_hours",
            "total_miles", "timeline", "remarks",
        ]
