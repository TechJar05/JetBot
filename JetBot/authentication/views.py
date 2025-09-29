
# users/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import UserRegisterSerializer, UserLoginSerializer
from django.contrib.auth import get_user_model

User = get_user_model()


class RegisterAPIView(APIView):
    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                "data": {
                    "message": "User registered successfully",
                    "user": serializer.data,
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }
            }, status=status.HTTP_201_CREATED)

        # Wrap errors
        error_messages = []
        for field, msgs in serializer.errors.items():
            for msg in msgs:
                error_messages.append(f"{field}: {msg}")

        return Response({
            "error": {
                "message": error_messages[0] if error_messages else "Invalid input"
            }
        }, status=status.HTTP_400_BAD_REQUEST)


class LoginAPIView(APIView):
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if not serializer.is_valid():
            # Wrap validation errors
            error_messages = []
            for field, msgs in serializer.errors.items():
                for msg in msgs:
                    error_messages.append(f"{field}: {msg}")

            return Response({
                "error": {
                    "message": error_messages[0] if error_messages else "Invalid input"
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        role = serializer.validated_data['role']

        user = authenticate(request, email=email, password=password)

        if user is not None and user.role == role:
            refresh = RefreshToken.for_user(user)
            return Response({
                "data": {
                    "message": "Login successful",
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "role": user.role,
                        "name": user.name,
                    },
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)

        return Response({
            "error": {
                "message": "Invalid credentials or role"
            }
        }, status=status.HTTP_401_UNAUTHORIZED)
