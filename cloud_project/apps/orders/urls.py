from django.urls import path

from apps.orders.views import OrderDetailAPIView, PurchaseVPSAPIView

urlpatterns = [
    path("purchase/", PurchaseVPSAPIView.as_view(), name="order-purchase"),
    path("<uuid:uuid>/", OrderDetailAPIView.as_view(), name="order-detail"),
]
