from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from authentication.models import Interview,Report
from .services import process_jd_file   # your PDF text extractor
from all_services.question_generator import generate_interview_questions  # ✅ new import
from rest_framework import generics
from .serializers import ReportSerializer
from openai import OpenAI
from django.conf import settings
import json

from django.utils import timezone
from authentication.models import Interview
from .services import process_jd_file   # your PDF text extractor
from all_services.question_generator import generate_interview_questions  # ✅ new import
client = OpenAI(api_key=settings.OPENAI_API_KEY)

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






class ReportCreateView(generics.CreateAPIView):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer

    def create(self, request, *args, **kwargs):
        interview_id = request.data.get("interview")
        if not interview_id:
            return Response({"error": "Interview ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure the interview exists
        try:
            interview = Interview.objects.get(id=interview_id)
        except Interview.DoesNotExist:
            return Response({"error": "Interview not found"}, status=status.HTTP_404_NOT_FOUND)

        # Prevent duplicate report for the same interview
        if hasattr(interview, "report"):
            return Response({"error": "Report already exists for this interview"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Fetch transcription
        transcription = getattr(interview, "full_transcript", None)
        if not transcription:
            return Response({"error": "Interview has no transcription"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Call OpenAI to analyze transcription
        try:
            prompt = f"""
            Analyze the following interview transcription and generate a structured report with:
            - key_strengths (list of dict: area, example, rating 1–5)
            - areas_for_improvement (list of dict: area, suggestions)
            - visual_feedback (list of dict: appearance, eye_contact, body_language if possible)
            - ratings (dict: technical, communication, problem_solving, time_mgmt, total)

            Transcription:
            {transcription}
            """

            response = client.chat.completions.create(
                model="gpt-4o-mini",  # or "gpt-4o" if available
                messages=[
                    {"role": "system", "content": "You are an expert HR interview evaluator."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_schema", "json_schema": {
                    "name": "interview_report",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "key_strengths": {"type": "array", "items": {"type": "object"}},
                            "areas_for_improvement": {"type": "array", "items": {"type": "object"}},
                            "visual_feedback": {"type": "array", "items": {"type": "object"}},
                            "ratings": {"type": "object"}
                        },
                        "required": ["key_strengths", "areas_for_improvement", "ratings"]
                    }
                }}
            )
            content = response.choices[0].message.content
            report_data = json.loads(content) 

        except Exception as e:
            return Response({"error": f"OpenAI API failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # ✅ Save report
        report = Report.objects.create(
            interview=interview,
            key_strengths=report_data.get("key_strengths"),
            areas_for_improvement=report_data.get("areas_for_improvement"),
            visual_feedback=report_data.get("visual_feedback"),
            ratings=report_data.get("ratings"),
        )

        serializer = self.get_serializer(report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)



class ReportListView(generics.ListAPIView):
    queryset = Report.objects.all().select_related("interview")  # optimize join
    serializer_class = ReportSerializer

