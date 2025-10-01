
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
from .models import PasswordResetOTP

User = get_user_model()


# 1️⃣ Send OTP
class SendOTPAPIView(APIView):
    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        otp = str(random.randint(100000, 999999))
        PasswordResetOTP.objects.create(user=user, otp=otp)

        send_mail(
            "Your Password Reset OTP",
            f"Your OTP is: {otp}. It is valid for 10 minutes.",
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )

        return Response({"data": "OTP sent to email"}, status=status.HTTP_200_OK)


# 2️⃣ Verify OTP with email
class VerifyOTPAPIView(APIView):
    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")

        if not email or not otp:
            return Response(
                {"error": "Email and OTP are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            otp_obj = PasswordResetOTP.objects.filter(user=user, otp=otp).latest("created_at")
        except PasswordResetOTP.DoesNotExist:
            return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        if otp_obj.is_expired():
            return Response({"error": "OTP expired"}, status=status.HTTP_400_BAD_REQUEST)

        otp_obj.verified = True
        otp_obj.save()

        return Response({"data": "OTP verified"}, status=status.HTTP_200_OK)


# 3️⃣ Reset Password
class ResetPasswordAPIView(APIView):
    def post(self, request):
        new_password = request.data.get("new_password")
        if not new_password:
            return Response({"error": "New password is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            otp_obj = PasswordResetOTP.objects.filter(verified=True).latest("created_at")
        except PasswordResetOTP.DoesNotExist:
            return Response({"error": "No verified OTP found"}, status=status.HTTP_400_BAD_REQUEST)

        user = otp_obj.user
        user.set_password(new_password)
        user.save()

        # Delete all OTPs for security
        PasswordResetOTP.objects.filter(user=user).delete()

        return Response({"data": "Password reset successful"}, status=status.HTTP_200_OK)
