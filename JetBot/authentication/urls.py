# users/urls.py
from django.urls import path
from .views import RegisterAPIView, LoginAPIView

urlpatterns = [
    path('student/register', RegisterAPIView.as_view(), name='student-register'),
    path('student/login', LoginAPIView.as_view(), name='student-login'),
]
