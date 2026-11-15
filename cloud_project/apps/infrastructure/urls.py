from django.urls import path

from apps.infrastructure.api.views import OperatingSystemListView

urlpatterns = [
    path("operating-systems/", OperatingSystemListView.as_view(), name="operating-system-list"),
]
