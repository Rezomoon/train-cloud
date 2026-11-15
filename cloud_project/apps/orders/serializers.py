from rest_framework import serializers

from apps.orders.models import Order, PaymentMethodChoices
from apps.vps.models import VPS


class OrderVPSDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = VPS
        fields = [
            "uuid",
            "name",
            "ip_address",
            "status",
            "cpu",
            "ram",
            "storage",
            "plan",
            "duration",
            "operating_system",
            "created_at",
        ]


class PurchaseVPSInputSerializer(serializers.Serializer):
    plan_uuid = serializers.UUIDField(required=True)
    duration_uuid = serializers.UUIDField(required=True)
    operating_system_uuid = serializers.UUIDField(required=False)
    vps_name = serializers.CharField(
        required=False,
        default="My VPS",
        max_length=100,
    )
    payment_method = serializers.ChoiceField(
        choices=PaymentMethodChoices.choices,
        required=False,
        default=PaymentMethodChoices.BANK,
    )


class PayOrderInputSerializer(serializers.Serializer):
    simulate_failure = serializers.BooleanField(required=False, default=False)


class OrderDetailSerializer(serializers.ModelSerializer):
    plan = serializers.UUIDField(source="plan_id", read_only=True)
    duration = serializers.UUIDField(source="duration_id", read_only=True)
    vps = OrderVPSDetailSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "uuid",
            "vps_name",
            "plan",
            "duration",
            "vps",
            "cpu_snapshot",
            "ram_snapshot",
            "storage_snapshot",
            "unit_price",
            "total_amount",
            "payment_method",
            "payment_status",
            "payment_reference",
            "status",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields
