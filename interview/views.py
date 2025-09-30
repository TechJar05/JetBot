from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from authentication.models import Interview, User, Report
from .serializers import InterviewSerializer, StudentSearchSerializer, ReportSerializer,InterviewTableSerializer,VisualFeedbackSerializer,InterviewRatingsSerializer
from .services import process_jd_file   # your PDF text extractor
from all_services.question_generator import generate_interview_questions, generate_chat_completion # LLM question gen
import json

def _can_view_or_own(user: User, interview: Interview) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "role", None) in ("admin", "super_admin"):
        return True
    return interview.student_id == user.id


class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "student"
        )
        

def _create_report_for_interview(interview: Interview) -> Report:
    """
    Idempotent report creation:
      - returns existing Report if present
      - raises ValueError if transcript missing
      - raises RuntimeError if LLM fails
    """
    # return existing if any
    try:
        return interview.report
    except Report.DoesNotExist:
        pass

    transcription = (interview.full_transcript or "").strip()
    if not transcription:
        raise ValueError("Interview has no transcription")

    prompt = f"""
    You are an expert HR interview evaluator.
    Analyze the following interview transcription and produce STRICT JSON with keys:
    - key_strengths: array of objects: {{ "area": str, "example": str, "rating": int (1-5) }}
    - areas_for_improvement: array of objects: {{ "area": str, "suggestions": str }}
    - visual_feedback: array of objects (optional): {{ "appearance": str, "eye_contact": str, "body_language": str }}
    - ratings: object: {{
        "technical": int (1-5),
        "communication": int (1-5),
        "problem_solving": int (1-5),
        "time_mgmt": int (1-5),
        "total": int
    }}
    Return ONLY compact JSON. No markdown, no prose.

    Transcription:
    {transcription}
    """

    try:
        raw_json = generate_chat_completion(
            prompt=prompt,
            model="gpt-4o-mini",
            max_tokens=1200,
            temperature=0.2,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "interview_report",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "key_strengths": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "area": {"type": "string"},
                                        "example": {"type": "string"},
                                        "rating": {"type": "integer"}
                                    },
                                    "required": ["area", "rating"]
                                }
                            },
                            "areas_for_improvement": {
                                "type": "array",
                                "items": {
                                    "type": "object"},
                            },
                            "visual_feedback": {
                                "type": "array",
                                "items": {
                                    "type": "object"}
                            },
                            "ratings": {
                                "type": "object",
                                "properties": {
                                    "technical": {"type": "integer"},
                                    "communication": {"type": "integer"},
                                    "problem_solving": {"type": "integer"},
                                    "time_mgmt": {"type": "integer"},
                                    "total": {"type": "integer"}
                                },
                                "required": ["technical","communication","problem_solving","time_mgmt","total"]
                            }
                        },
                        "required": ["key_strengths", "areas_for_improvement", "ratings"],
                        "additionalProperties": False
                    }
                }
            }
        )
        data = json.loads(raw_json)
    except Exception as exc:
        raise RuntimeError(f"LLM failed: {exc}")

    report = Report.objects.create(
        interview=interview,
        key_strengths=data.get("key_strengths"),
        areas_for_improvement=data.get("areas_for_improvement"),
        visual_feedback=data.get("visual_feedback"),
        ratings=data.get("ratings"),
    )
    return report
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

class ReportCreateView(generics.CreateAPIView):
    """
    Admin generates a report by interview id (manual trigger).
    Body: { "interview": <id> }
    """
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    permission_classes = [IsAdminOrSuperAdmin]

    def create(self, request, *args, **kwargs):
        interview_id = request.data.get("interview")
        if not interview_id:
            return Response({"error": "Interview ID is required"}, status=400)

        interview = get_object_or_404(Interview, id=interview_id)
        try:
            report = _create_report_for_interview(interview)
        except ValueError as ve:
            return Response({"error": str(ve)}, status=400)
        except RuntimeError as re:
            return Response({"error": str(re)}, status=500)

        return Response(ReportSerializer(report).data, status=201)


class CompleteInterviewAndGenerateReportAPIView(APIView):
    """
    POST /api/interviews/<interview_id>/complete-and-generate-report/
    Marks interview completed (if not already) and creates the report (idempotent).
    Who can call: student (owner), admin, super_admin.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, interview_id, *args, **kwargs):
        interview = get_object_or_404(
            Interview.objects.select_related("student"), id=interview_id
        )

        if not _can_view_or_own(request.user, interview):
            return Response({"error": "Forbidden"}, status=403)

        if interview.status != "completed":
            interview.status = "completed"
            interview.save(update_fields=["status"])

        try:
            report = _create_report_for_interview(interview)
            created = True
        except ValueError as ve:
            return Response({"error": str(ve)}, status=400)
        except RuntimeError as re:
            return Response({"error": str(re)}, status=500)
        except Exception:
            # if already created in race condition, return it
            try:
                report = interview.report
                created = False
            except Report.DoesNotExist:
                return Response({"error": "Unknown error creating report"}, status=500)

        return Response(ReportSerializer(report).data, status=201 if created else 200)


from .serializers import ReportListSerializer


class ReportListView(generics.ListAPIView):
    """
    Admin: all reports
    Student: only their reports
    """
    serializer_class = ReportListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Report.objects.select_related("interview", "interview__student")  # join with interview and student

        if not user.is_authenticated:
            return Report.objects.none()

        if getattr(user, "role", None) in ("admin", "super_admin"):
            return qs.order_by("-created_at")  # Admin sees all reports, ordered by created_at

        # Only return the reports that belong to the logged-in student
        return qs.filter(interview__student=user).order_by("-created_at")  # Student only sees their own reports

class ReportDetailView(generics.RetrieveAPIView):
    """
    GET /api/reports/<report_id>/
    Admin/super_admin: any
    Student: only their own
    """
    queryset = Report.objects.select_related("interview", "interview__student")
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def retrieve(self, request, *args, **kwargs):
        report = self.get_object()
        if not _can_view_or_own(request.user, report.interview):
            return Response({"error": "Forbidden"}, status=403)
        return Response(self.get_serializer(report).data, status=200)


class ReportByInterviewView(generics.GenericAPIView):
    """
    GET /api/reports/by-interview/<interview_id>/
    Fetch report JSON by interview (student own / admin any).
    """
    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, interview_id, *args, **kwargs):
        interview = get_object_or_404(
            Interview.objects.select_related("student"), id=interview_id
        )
        if not _can_view_or_own(request.user, interview):
            return Response({"error": "Forbidden"}, status=403)
        try:
            report = interview.report
        except Report.DoesNotExist:
            return Response({"error": "Report not generated yet"}, status=404)
        return Response(ReportSerializer(report).data, status=200)
    

class MyInterviewsListView(generics.ListAPIView):
    """
    GET /api/my/interviews/?status=pending|ongoing|completed  (optional)
    Returns ONLY the authenticated student's interviews.
    Sorted: upcoming first (by scheduled_time asc), then past (desc).
    """
    serializer_class = InterviewSerializer
    permission_classes = [permissions.IsAuthenticated, IsStudent]

    def get_queryset(self):
        user = self.request.user
        qs = Interview.objects.filter(student=user)

        # Optional status filter
        status_param = self.request.query_params.get("status")
        valid_status = {c[0] for c in Interview.STATUS_CHOICES}
        if status_param:
            if status_param not in valid_status:
                # empty queryset for invalid status
                return Interview.objects.none()
            qs = qs.filter(status=status_param)

        # Order: upcoming first (soonest), then past (newest)
        upcoming = qs.filter(scheduled_time__gte=now()).order_by("scheduled_time")
        past = qs.filter(scheduled_time__lt=now()).order_by("-scheduled_time")
        return upcoming.union(past)





from django.db.models import Count
from django.db.models.functions import TruncDate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

#  admin side analytic report
class InterviewAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = {}

        # 1. Interview Status Distribution (Completed vs Scheduled)
        status_counts = Interview.objects.values("status").annotate(count=Count("id"))

        completed_count = 0
        scheduled_count = 0

        for item in status_counts:
            if item["status"] == "completed":
                completed_count += item["count"]
            else:  # pending + ongoing = scheduled
                scheduled_count += item["count"]

        total_interviews = completed_count + scheduled_count

        status_distribution = []
        if total_interviews > 0:
            status_distribution = [
                {
                    "status": "completed",
                    "count": completed_count,
                    "percentage": round((completed_count / total_interviews) * 100, 2),
                },
                {
                    "status": "scheduled",
                    "count": scheduled_count,
                    "percentage": round((scheduled_count / total_interviews) * 100, 2),
                },
            ]

        data["status_distribution"] = status_distribution

        # 2. Difficulty Level Distribution
        difficulty_counts = Interview.objects.values("difficulty_level").annotate(count=Count("id"))
        data["difficulty_distribution"] = list(difficulty_counts)

        # 3. Top 3 Centers by Student Count
        top_centers = (
            User.objects.values("center")
            .annotate(student_count=Count("id"))
            .order_by("-student_count")[:3]
        )
        data["top_centers"] = list(top_centers)

        # 4. Daily Interview Count
        daily_counts = (
            Interview.objects.annotate(date=TruncDate("scheduled_time"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )
        data["daily_interview_count"] = list(daily_counts)

        return Response(data)




#  student dashboard analytic report
class StudentAnalyticsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        # Ensure student exists
        try:
            student = User.objects.get(id=student_id, role='student')
        except User.DoesNotExist:
            return Response({"error": "Student not found"}, status=404)
        
        # Get all completed interviews for this student
        completed_interviews = Interview.objects.filter(student=student, status='completed')
        
        if not completed_interviews.exists():
            return Response({
                "total_average_rating": 0,
                "completed_interviews": 0,
                "skill_breakdown": {
                    "technical": 0,
                    "communication": 0,
                    "problem_solving": 0,
                    "time_mgmt": 0
                },
                "interview_ratings": []
            })

        # Collect ratings from each interview
        ratings_list = []
        total_technical = total_communication = total_problem = total_time = 0
        count = 0
        
        for interview in completed_interviews:
            report = getattr(interview, "report", None)
            if report and report.ratings:
                r = report.ratings
                # Assuming ratings keys: technical, communication, problem_solving, time_mgmt
                technical = r.get('technical', 0)
                communication = r.get('communication', 0)
                problem_solving = r.get('problem_solving', 0)
                time_mgmt = r.get('time_mgmt', 0)
                
                # Rating out of 10 (sum all / 4)
                avg_rating = round((technical + communication + problem_solving + time_mgmt)/4, 2)
                ratings_list.append({
                    "interview_id": interview.id,
                    "rating_out_of_10": avg_rating
                })
                
                # Sum for overall average
                total_technical += technical
                total_communication += communication
                total_problem += problem_solving
                total_time += time_mgmt
                count += 1
        
        # Total average rating across all interviews
        total_average_rating = round((total_technical + total_communication + total_problem + total_time) / (count*4), 2)
        
        # Skill breakdown average
        skill_breakdown = {
            "technical": round(total_technical / count, 2),
            "communication": round(total_communication / count, 2),
            "problem_solving": round(total_problem / count, 2),
            "time_mgmt": round(total_time / count, 2)
        }
        
        return Response({
            "total_average_rating": total_average_rating,
            "completed_interviews": count,
            "skill_breakdown": skill_breakdown,
            "interview_ratings": ratings_list
        })






#  admin side table data 
class InterviewTableAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        interviews = Interview.objects.select_related('student', 'report').all().order_by('-scheduled_time')

        interview_table = InterviewTableSerializer(interviews, many=True).data
        interview_ratings = InterviewRatingsSerializer(interviews, many=True).data
        visual_feedback = VisualFeedbackSerializer(interviews, many=True).data

        return Response({
            "interview_table": interview_table,
            "interview_ratings": interview_ratings,
            "visual_feedback": visual_feedback
        })