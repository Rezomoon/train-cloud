from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.orders.serializers import (
    OrderDetailSerializer,
    PurchaseVPSInputSerializer,
)
from apps.orders.services import create_purchase_order


class PurchaseVPSAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PurchaseVPSInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = create_purchase_order(
            user=request.user,
            plan_uuid=data["plan_uuid"],
            duration_uuid=data["duration_uuid"],
            operating_system_uuid=data.get("operating_system_uuid"),
            vps_name=data.get("vps_name"),
            payment_method=data.get("payment_method"),
        )

        return Response(
            OrderDetailSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class OrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, uuid):
        order = get_object_or_404(Order, uuid=uuid, user=request.user)
        return Response(
            OrderDetailSerializer(order).data,
            status=status.HTTP_200_OK,
        )
