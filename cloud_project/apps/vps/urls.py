from django.urls import path
from apps.vps.api.views import VPSPlansView
urlpatterns = [
    path("plans/", VPSPlansView.as_view(), name="vps-plans"),
]