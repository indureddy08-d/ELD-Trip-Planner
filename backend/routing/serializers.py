from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=255, trim_whitespace=True)
    pickup_location  = serializers.CharField(max_length=255, trim_whitespace=True)
    dropoff_location = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate(self, data):
        if data["pickup_location"].lower() == data["dropoff_location"].lower():
            raise serializers.ValidationError(
                {"dropoff_location": "Pickup and dropoff cannot be the same location."}
            )
        return data


class CoordinateSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class RouteLegSerializer(serializers.Serializer):
    from_label      = serializers.CharField()
    to_label        = serializers.CharField()
    distance_miles  = serializers.FloatField()
    duration_hours  = serializers.FloatField()
    coordinates     = CoordinateSerializer(many=True)


class RouteResultSerializer(serializers.Serializer):
    total_distance_miles  = serializers.FloatField()
    total_duration_hours  = serializers.FloatField()
    legs                  = RouteLegSerializer(many=True)
    provider              = serializers.CharField()
    from_cache            = serializers.BooleanField()
