from rest_framework.serializers import ModelSerializer
from apps.vps.models import Plan
#
class VPSPlanSerializer(ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"