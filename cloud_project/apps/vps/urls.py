from django.urls import path
from apps.vps.api.views import (
    VPSPlansView,
    VPSPlanDetailView,
    DurationListView,
    PurchaseVPSView,
    VPSListView,
)
urlpatterns = [
    path("", VPSListView.as_view(), name="vps-list"),
    path("plans/", VPSPlansView.as_view(), name="vps-plans"),
    path("plans/<uuid:plan_id>/", VPSPlanDetailView.as_view(), name="vps-plan-detail"),
    path("durations/", DurationListView.as_view(), name="vps-durations"),
    path("purchase/", PurchaseVPSView.as_view(), name="vps-purchase")
]
