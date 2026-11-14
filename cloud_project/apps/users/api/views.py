from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from apps.users.serializers import LoginUserSerializer, UserCreateSerializer
from rest_framework_simplejwt.tokens import RefreshToken
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
