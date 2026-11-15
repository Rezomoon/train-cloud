from rest_framework import serializers

from apps.orders.models import Order, PaymentMethodChoices


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


class OrderDetailSerializer(serializers.ModelSerializer):
    plan = serializers.UUIDField(source="plan_id", read_only=True)
    duration = serializers.UUIDField(source="duration_id", read_only=True)

    class Meta:
        model = Order
        fields = [
            "uuid",
            "vps_name",
            "plan",
            "duration",
            "cpu_snapshot",
            "ram_snapshot",
            "storage_snapshot",
            "unit_price",
            "total_amount",
            "payment_method",
            "payment_status",
            "status",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields
