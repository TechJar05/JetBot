from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from authentication.models import Interview, User
from .serializers import InterviewSerializer
from .services import process_jd_file
from datetime import timedelta

class ScheduleInterviewAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """
        Student schedules and immediately starts interview.
        Takes student info, JD text or file, and creates Interview record.
        """
        user = request.user
        if user.role != "student":
            return Response({"error": {"message": "Only students can schedule interviews"}},
                            status=status.HTTP_403_FORBIDDEN)

        jd_text = request.data.get("jd", "")
        jd_file = request.FILES.get("jd_file")

        if jd_file:
            jd_text = process_jd_file(jd_file)

        interview = Interview.objects.create(
            student=user,
            jd=jd_text,
            difficulty_level=request.data.get("difficulty_level", "beginner"),
            scheduled_time=request.data.get("scheduled_time"),
            duration_minutes=request.data.get("duration_minutes", 20),
            status="ongoing",  # immediately start interview
        )

        serializer = InterviewSerializer(interview)
        return Response({
            "data": {
                "message": "Interview scheduled and started successfully",
                "interview": serializer.data
            }
        }, status=status.HTTP_201_CREATED)
