from django.urls import path
from apps.vps.api.views import VPSPlansView, VPSPlanDetailView
urlpatterns = [
    path("plans/", VPSPlansView.as_view(), name="vps-plans"),
    path("plans/<int:plan_id>/", VPSPlanDetailView.as_view(), name="vps-plan-detail"),
]