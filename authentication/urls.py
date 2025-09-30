# users/urls.py
from django.urls import path
from .views import RegisterAPIView, LoginAPIView,ForgotPasswordAPIView,ResetPasswordAPIView

urlpatterns = [
    path('student/register', RegisterAPIView.as_view(), name='student-register'),
    path('student/login', LoginAPIView.as_view(), name='student-login'),
        path("forgot-password/", ForgotPasswordAPIView.as_view(), name="forgot-password"),
    path("reset-password/", ResetPasswordAPIView.as_view(), name="reset-password"),
]
