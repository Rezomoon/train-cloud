from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.vps.models import VPS
from apps.vps.serializers import VPSPlanSerializer, VPSSerializer, DurationSerializer
from apps.vps.queries import all_vps_plans, get_vps_plan_by_id, all_durations, get_duration_by_id, user_vps_list, get_vps_by_id
from apps.vps.services import request_vps_termination
# Create your views here.


class VPSListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        vps_list = user_vps_list(user)
        serializer = VPSSerializer(vps_list, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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




class DurationListView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        durations = all_durations()
        serializer = DurationSerializer(durations, many=True)

        return Response(serializer.data,status=status.HTTP_200_OK)

class PurchaseVPSView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Implement the logic to handle VPS purchase here
        data = request.data
        user = request.user
        serializer = VPSPlanSerializer(data=data)
        if serializer.is_valid():
            serializer.save(user=user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VPSDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, vps_id):
        vps = get_vps_by_id(vps_id)
        if not vps:
            return Response({"detail": "VPS not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = VPSSerializer(vps)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TerminateVPSAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, vps_id):
        vps = request_vps_termination(user=request.user, vps_uuid=vps_id)
        serializer = VPSSerializer(vps)
        return Response(
            {
                "detail": "VPS termination request accepted.",
                "vps": serializer.data,
            },
            status=status.HTTP_202_ACCEPTED,
        )