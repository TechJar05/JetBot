from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404

from authentication.models import Interview, User
from .serializers import InterviewSerializer, StudentSearchSerializer
from .services import process_jd_file   # your PDF text extractor
from all_services.question_generator import generate_interview_questions  # LLM question gen


# -----------------------------
# Permissions
# -----------------------------
class IsAdminOrSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in ("admin", "super_admin")
        )


# -----------------------------
# Admin-only: Schedule Interview
# -----------------------------
class ScheduleInterviewAPIView(APIView):
    """
    Admin schedules an interview for a student.
    Requires:
      - form-data: student (id), jd (file) OR jd_text
      - optional: difficulty_level, duration_minutes, scheduled_time
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        # Target student (must be role=student)
        student_id = request.data.get("student")
        if not student_id:
            return Response({"error": "Student ID is required (field: student)"}, status=status.HTTP_400_BAD_REQUEST)
        student = get_object_or_404(User, id=student_id, role="student")

        # JD: accept file or raw text (prefer file if both provided)
        jd_file = request.FILES.get("jd")
        jd_text = request.data.get("jd_text")

        if not jd_file and not jd_text:
            return Response({"error": "Provide JD file (jd) or jd_text"}, status=status.HTTP_400_BAD_REQUEST)

        if jd_file:
            try:
                jd_text = process_jd_file(jd_file)
            except Exception as e:
                return Response({"error": f"Failed to parse JD file: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        difficulty_level = request.data.get("difficulty_level", "beginner")
        valid_diff = [c[0] for c in Interview.DIFFICULTY_CHOICES]
        if difficulty_level not in valid_diff:
            return Response(
                {"error": f"Invalid difficulty_level. Choose one of: {', '.join(valid_diff)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            duration = int(request.data.get("duration_minutes", 30))
        except (TypeError, ValueError):
            return Response({"error": "duration_minutes must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        scheduled_time = request.data.get("scheduled_time") or timezone.now()

        # Generate questions (do not block if it fails)
        try:
            questions = generate_interview_questions(jd_text, difficulty_level)
        except Exception:
            questions = []

        interview = Interview.objects.create(
            student=student,
            jd=jd_text,
            difficulty_level=difficulty_level,
            scheduled_time=scheduled_time,
            duration_minutes=duration,
            status="pending",
            questions=questions,
        )

        return Response(
            {
                "message": "Interview scheduled successfully",
                "interview": InterviewSerializer(interview).data,
                "questions": questions,
            },
            status=status.HTTP_201_CREATED,
        )


# -----------------------------
# Debounced student search (for autofill)
# -----------------------------
class SearchStudentAPIView(APIView):
    """
    GET /api/students/search/?q=<term>
    Returns top 10 students matching name or email.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, *args, **kwargs):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response([], status=status.HTTP_200_OK)

        students = (
            User.objects.filter(
                role="student"
            ).filter(
                Q(name__icontains=query) | Q(email__icontains=query)
            )
            .only("id", "name", "email")  # minimal fields for speed
            .order_by("name")[:10]
        )

        serializer = StudentSearchSerializer(students, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# -----------------------------
# (Optional) Student detail for full autofill on selection
# -----------------------------
class StudentDetailAPIView(APIView):
    """
    GET /api/students/<id>/
    Returns full student fields needed to auto-fill the form.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, student_id, *args, **kwargs):
        student = get_object_or_404(User, id=student_id, role="student")
        data = {
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "mobile_no": student.mobile_no,
            "course_name": student.course_name,
            "center": student.center,
            "batch_no": student.batch_no,
        }
        return Response(data, status=status.HTTP_200_OK)
