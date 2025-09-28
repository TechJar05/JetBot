from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from authentication.models import Interview
from .services import process_jd_file   # your PDF text extractor
from all_services.question_generator import generate_interview_questions  # ✅ new import


class ScheduleInterviewAPIView(APIView):
    def post(self, request, *args, **kwargs):
        user = request.user  # logged-in student

        # ✅ Get JD file
        jd_file = request.FILES.get("jd")
        if not jd_file:
            return Response({"error": "Job description file is required"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Parse JD text using your PyMuPDF extractor
        jd_text = process_jd_file(jd_file)

        difficulty_level = request.data.get("difficulty_level", "beginner")
        duration = request.data.get("duration_minutes", 30)

        scheduled_time = request.data.get("scheduled_time")
        if not scheduled_time:
            scheduled_time = timezone.now()

        # ✅ Generate questions using LLM service
        questions = generate_interview_questions(jd_text, difficulty_level)

        interview = Interview.objects.create(
            student=user,
            jd=jd_text,
            difficulty_level=difficulty_level,
            scheduled_time=scheduled_time,
            duration_minutes=duration,
            status="pending",
            questions=questions,   # ✅ now stored directly
        )

        return Response(
            {
                "message": "Interview scheduled successfully",
                "id": interview.id,
                "difficulty": interview.difficulty_level,
                "scheduled_time": interview.scheduled_time,
                "questions": questions,  # ✅ return to frontend
            },
            status=status.HTTP_201_CREATED,
        )
