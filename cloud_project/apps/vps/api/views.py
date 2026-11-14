from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.vps.serializers import VPSPlanSerializer
from apps.vps.queries import all_vps_plans
# Create your views here.

class VPSPlansView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        query = all_vps_plans()
        serializer = VPSPlanSerializer(query, many=True)
        return Response(serializer.data)