from rest_framework.serializers import ModelSerializer
from apps.vps.models import Plan, VPS, Duration


class VPSPlanSerializer(ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"


class VPSSerializer(ModelSerializer):
    class Meta:
        model = VPS
        fields = [
            "uuid",
            "name",
            "user",
            "plan",
            "duration",
            "operating_system",
            "provider_instance_id",
            "ip_address",
            "status",
            "cpu",
            "ram",
            "storage",
            "created_at",
            "updated_at",
        ]


class DurationSerializer(ModelSerializer):
    class Meta:
        model = Duration
        fields = [
            "uuid",
            "name",
            "duration_in_month",
            "data_center",
        ]
