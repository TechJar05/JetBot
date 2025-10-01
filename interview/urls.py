from django.urls import path
from .views import ScheduleInterviewAPIView, SearchStudentAPIView,StudentDetailAPIView, ReportByInterviewView, ReportCreateView, ReportDetailView, ReportListView, CompleteInterviewAndGenerateReportAPIView, MyInterviewsListView,InterviewAnalyticsAPIView,StudentAnalyticsAPIView,InterviewTableAPIView,ParseJDAPIView
urlpatterns = [
    path("parse-jd/", ParseJDAPIView.as_view(), name="parse-jd"),
    path("schedule", ScheduleInterviewAPIView.as_view(), name="schedule-interview"),
    path("students/search", SearchStudentAPIView.as_view(), name="search-students"),
    path("students/<int:student_id>", StudentDetailAPIView.as_view(), name="student-detail"),
    path("reports", ReportListView.as_view(), name="report-list"),
    path("reports/create", ReportCreateView.as_view(), name="report-create"),
    path("reports/<int:pk>", ReportDetailView.as_view(), name="report-detail"),
    path("reports/by-interview/<int:interview_id>", ReportByInterviewView.as_view(), name="report-by-interview"),
    path("<int:interview_id>/complete-and-generate-report",
         CompleteInterviewAndGenerateReportAPIView.as_view(),
         name="interview-complete-and-generate-report"),
    
    path("my", MyInterviewsListView.as_view(), name="my-interviews"),
    
    path("analytics", InterviewAnalyticsAPIView.as_view(), name="interview-analytics"),
    path('analytics/student/<int:student_id>', StudentAnalyticsAPIView.as_view(), name='student-analytics'),
    path('interview-table-data', InterviewTableAPIView.as_view(), name='interview-analytics'),
]
