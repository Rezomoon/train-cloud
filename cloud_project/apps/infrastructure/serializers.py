from rest_framework.serializers import ModelSerializer
from apps.infrastructure.models import OperatingSystem , Region, DataCenter

#

class OperatingSystemSerializer(ModelSerializer):
    class Meta:
        model = OperatingSystem
        fields = "__all__"