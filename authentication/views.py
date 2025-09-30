
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






import random
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import get_user_model
from authentication.models import PasswordResetOTP
from .serializers import ForgotPasswordSerializer, ResetPasswordSerializer

User = get_user_model()


class ForgotPasswordAPIView(APIView):
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response(
                    {"error": {"message": "User not found"}},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Generate 6-digit OTP
            otp = str(random.randint(100000, 999999))
            PasswordResetOTP.objects.create(user=user, otp=otp)

            # Send OTP email
            send_mail(
                "Your Password Reset OTP",
                f"Your OTP for resetting password is: {otp}. It is valid for 10 minutes.",
                settings.DEFAULT_FROM_EMAIL,
                [email],
            )

            return Response({"data": {"message": "OTP sent to email"}}, status=status.HTTP_200_OK)

        return Response({"error": {"message": serializer.errors}}, status=status.HTTP_400_BAD_REQUEST)


class ResetPasswordAPIView(APIView):
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp = serializer.validated_data['otp']
            new_password = serializer.validated_data['new_password']

            try:
                user = User.objects.get(email=email)
                otp_obj = PasswordResetOTP.objects.filter(user=user, otp=otp).latest("created_at")
            except (User.DoesNotExist, PasswordResetOTP.DoesNotExist):
                return Response({"error": {"message": "Invalid OTP"}}, status=status.HTTP_400_BAD_REQUEST)

            if otp_obj.is_expired():
                return Response({"error": {"message": "OTP expired"}}, status=status.HTTP_400_BAD_REQUEST)

            # Reset password
            user.set_password(new_password)
            user.save()

            # Delete all OTPs for security
            PasswordResetOTP.objects.filter(user=user).delete()

            return Response({"data": {"message": "Password reset successful"}}, status=status.HTTP_200_OK)

        return Response({"error": {"message": serializer.errors}}, status=status.HTTP_400_BAD_REQUEST)
