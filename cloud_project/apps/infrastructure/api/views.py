from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.infrastructure.queries import all_active_operating_systems
from apps.infrastructure.serializers import OperatingSystemSerializer

# 

class OperatingSystemListView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        operating_systems = all_active_operating_systems()
        serializer = OperatingSystemSerializer(operating_systems, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)