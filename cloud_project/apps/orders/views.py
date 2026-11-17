from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.orders.serializers import (
    OrderDetailSerializer,
    OrderVPSDetailSerializer,
    PayOrderInputSerializer,
    PurchaseVPSInputSerializer,
)
from apps.orders.services import create_purchase_order, process_order_payment

from apps.orders.queries import get_user_orders

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


class PayOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, uuid):
        input_serializer = PayOrderInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        order, gateway_payload = process_order_payment(
            user=request.user,
            order_uuid=uuid,
            simulate_failure=input_serializer.validated_data[
                "simulate_failure"
            ],
        )

        vps_data = (
            OrderVPSDetailSerializer(order.vps).data
            if order.vps_id
            else None
        )

        response_status = (
            status.HTTP_200_OK
            if gateway_payload["success"]
            else status.HTTP_400_BAD_REQUEST
        )

        return Response(
            {
                "order": OrderDetailSerializer(order).data,
                "payment_gateway_response": gateway_payload,
                "vps": vps_data,
            },
            status=response_status,
        )


class OrdersListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = get_user_orders(request.user)
        serializer = OrderDetailSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

