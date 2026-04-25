from django.urls import path
from .views import health_check, PlanTripView, TripDetailView, TripListView

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("trips/", TripListView.as_view(), name="trip_list"),
    path("trips/plan/", PlanTripView.as_view(), name="plan_trip"),
    path("trips/<int:trip_id>/", TripDetailView.as_view(), name="trip_detail"),
]
