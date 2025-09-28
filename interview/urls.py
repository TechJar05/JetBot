from django.urls import path
from .views import ScheduleInterviewAPIView, SearchStudentAPIView,StudentDetailAPIView

urlpatterns = [
    path("schedule", ScheduleInterviewAPIView.as_view(), name="schedule-interview"),
    path("students/search", SearchStudentAPIView.as_view(), name="search-students"),
    path("students/<int:student_id>", StudentDetailAPIView.as_view(), name="student-detail"),
]
