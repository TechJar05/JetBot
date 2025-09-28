from django.urls import path
from .views import ScheduleInterviewAPIView,ReportCreateView,ReportListView

urlpatterns = [
    path("schedule/", ScheduleInterviewAPIView.as_view(), name="schedule-interview"),
    path("reports/create/", ReportCreateView.as_view(), name="report-create"),
     path("reports/", ReportListView.as_view(), name="report-list"),
]
