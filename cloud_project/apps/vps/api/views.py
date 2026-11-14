from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.vps.serializers import VPSPlanSerializer
from apps.vps.queries import all_vps_plans, get_vps_plan_by_id
# Create your views here.


class VPSPlansView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        query = all_vps_plans()
        serializer = VPSPlanSerializer(query, many=True)
        return Response(serializer.data)

class VPSPlanDetailView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, plan_id):
        query = get_vps_plan_by_id(plan_id)
        if not query:
            return Response({"detail": "VPS Plan not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = VPSPlanSerializer(query)
        return Response(serializer.data)