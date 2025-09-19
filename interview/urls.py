from django.urls import path
from .views import ScheduleInterviewAPIView

urlpatterns = [
    path("schedule/", ScheduleInterviewAPIView.as_view(), name="schedule-interview"),
]
