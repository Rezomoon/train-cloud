from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apps.users.serializers import LoginUserSerializer, UserCreateSerializer, UserSerializer, UserProfileSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.queris import all_users
from apps.users.permissions import IsAdminUser
#
def generate_main_token(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}

class LoginView(APIView):
    permission_classes = [
        AllowAny,
    ]
    def post(self, request):
        data = request.data
        serializer = LoginUserSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        tokens = generate_main_token(user)
        return Response(
            {
                "message": "Login successful",
                "user": {
                    "id": user.id,
                    "mobile": user.mobile,
                    "role": user.role,
                },
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )

class RegisterUserView(APIView):
    permission_classes = [
        AllowAny,
    ]
    def post(self, request):
        data = request.data
        serializer = UserCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User registered successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserListView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        query = all_users()
        serializer = UserSerializer(query, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
