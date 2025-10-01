# users/urls.py
from django.urls import path
from .views import RegisterAPIView, LoginAPIView,SendOTPAPIView,ResetPasswordAPIView,VerifyOTPAPIView

urlpatterns = [
    path('student/register', RegisterAPIView.as_view(), name='student-register'),
    path('student/login', LoginAPIView.as_view(), name='student-login'),
    path("send-otp/", SendOTPAPIView.as_view(), name="send-otp"),
    path("verify-otp/", VerifyOTPAPIView.as_view(), name="verify-otp"),
    path("reset-password/", ResetPasswordAPIView.as_view(), name="reset-password"),
]
