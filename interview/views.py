from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils.timezone import now, datetime, timedelta
from authentication.models import Interview, User, Report
from .serializers import InterviewSerializer, StudentSearchSerializer, ReportSerializer,InterviewTableSerializer,VisualFeedbackSerializer,InterviewRatingsSerializer
from .services import process_jd_file   # your PDF text extractor
from all_services.question_generator import generate_interview_questions, generate_chat_completion # LLM question gen
import json
from all_services.visual_feedback_service import analyze_frames_aggregated, analyze_interview_metadata
from authentication.models import Interview
from all_services.frames import append_frames_to_cache,pop_frames_from_cache
from typing import Any, Dict, List, Optional
from all_services.pagination import ReportCursorPagination
from django.db.models import Count
from django.db.models.functions import TruncDate
from authentication.models import Interview, Report, User
import io
from django.http import HttpResponse
import pandas as pd
from .serializers import (InterviewTableSerializer,InterviewRatingsSerializer,VisualFeedbackSerializer,)



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
        

# views.py - Updated _create_report_for_interview function

def _create_report_for_interview(
    interview: Interview,
    frames: Optional[List[str]] = None,
) -> Report:
    """
    Create comprehensive interview report with GPT Vision-based visual feedback.
    Includes validation to prevent empty reports.
    """
    # Return existing report if already created (idempotent)
    try:
        return interview.report
    except Report.DoesNotExist:
        pass

    transcription = (interview.full_transcript or "").strip()
    
    # Validation: Ensure transcript has meaningful content
    if not transcription or len(transcription) < 50:
        raise ValueError(
            f"Interview transcription is too short ({len(transcription)} chars). "
            "Minimum 50 characters required for analysis."
        )

    print(f"Generating report for interview {interview.id}")
    print(f"Transcript length: {len(transcription)} characters")

    # 1️⃣ Generate text-based interview analysis
    prompt = f"""
You are an expert HR interview evaluator.

Analyze the following interview transcription and produce STRICT JSON with these keys:
- key_strengths: array of objects: {{ "area": str, "example": str, "rating": int (1–5) }}
- areas_for_improvement: array of objects: {{ "area": str, "suggestions": str }}
- ratings: object: {{
    "technical": int (1–5),
    "communication": int (1–5),
    "problem_solving": int (1–5),
    "time_mgmt": int (1–5),
    "total": int
}}

🧠 Evaluation Rules (Balanced & Fair):

1. **Repetition Rule (refined):**
   - Count as “repetition” only when the candidate literally restates the interviewer’s question or uses 5+ identical consecutive words from it without adding new information.
   - Do NOT penalize partial echoes or natural rephrasing (e.g., “Yes, I can tell you about my experience...”).
   - Ignore filler or verbal noise (e.g., “uh”, “snip”, “hmm”, “er”) unless it dominates the response.

2. **Answer Quality:**
   - Evaluate based on how well answers address the questions with clarity, structure, and relevance.
   - If a few answers are incomplete or unclear → lower related areas moderately (e.g., 3 instead of 4).
   - Apply lowest ratings (1–2) only when **most** answers are irrelevant, incoherent, or repeated.

3. **Scoring Logic:**
   - If most answers are coherent and technical → total score should be 12–16 (average to good range).
   - Only give total ≤10 when the majority of responses are non-answers or irrelevant.
   - Reward clear explanations, real examples, and structured thinking.

4. **Technical Evaluation:**
   - Technical score should reflect accuracy, specificity, and practical examples (not buzzwords).
   - If there are no clear technical examples, cap technical ≤2.

5. **Communication & Problem Solving:**
   - Communication focuses on clarity, fluency, and logical flow.
   - Problem solving measures analytical steps and structured troubleshooting.
   - Both can still score 3–4 even with one weak answer if others are solid.

6. **Time Management:**
   - Estimate based on how concise and focused the responses appear (avoid rambling or confusion).

💡 Important:
- Always mention **2 strengths** and **2 improvement areas**, even for weaker candidates.
- Return **only compact JSON** (no markdown, no prose, no explanations).
- Be strict but balanced — a few unclear answers shouldn’t drastically reduce all scores.

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
                                },
                                "minItems": 1  # Ensure at least 1 item
                            },
                            "areas_for_improvement": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "area": {"type": "string"},
                                        "suggestions": {"type": "string"}
                                    },
                                    "required": ["area"]
                                },
                                "minItems": 1
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
        
        data: Dict[str, Any] = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
        
        # Validate the response has meaningful data
        key_strengths = data.get("key_strengths", [])
        areas_for_improvement = data.get("areas_for_improvement", [])
        ratings = data.get("ratings", {})
        
        # Check if GPT returned empty arrays
        if not key_strengths or len(key_strengths) == 0:
            print("WARNING: GPT returned empty key_strengths, generating fallback...")
            key_strengths = [
                {
                    "area": "Communication",
                    "example": "Candidate participated in the interview process",
                    "rating": 3
                },
                {
                    "area": "Engagement",
                    "example": "Candidate responded to interview questions",
                    "rating": 3
                }
            ]
        
        if not areas_for_improvement or len(areas_for_improvement) == 0:
            print("WARNING: GPT returned empty areas_for_improvement, generating fallback...")
            areas_for_improvement = [
                {
                    "area": "Response Depth",
                    "suggestions": "Provide more detailed and elaborate answers to questions"
                },
                {
                    "area": "Technical Clarity",
                    "suggestions": "Use specific examples when discussing technical concepts"
                }
            ]
        
        if not ratings or not all(k in ratings for k in ["technical", "communication", "problem_solving", "time_mgmt"]):
            print("WARNING: GPT returned incomplete ratings, generating fallback...")
            ratings = {
                "technical": 3,
                "communication": 3,
                "problem_solving": 3,
                "time_mgmt": 3,
                "total": 12
            }
        
        # Ensure total is calculated
        if "total" not in ratings or ratings["total"] == 0:
            ratings["total"] = sum([
                ratings.get("technical", 0),
                ratings.get("communication", 0),
                ratings.get("problem_solving", 0),
                ratings.get("time_mgmt", 0)
            ])
        
        print(f"Report data validated:")
        print(f"  Key strengths: {len(key_strengths)}")
        print(f"  Areas for improvement: {len(areas_for_improvement)}")
        print(f"  Total rating: {ratings.get('total', 0)}")
        
    except Exception as exc:
        import traceback
        print(f"LLM analysis failed: {exc}")
        print(traceback.format_exc())
        raise RuntimeError(f"Failed to generate interview analysis: {exc}")

    # 2️⃣ Get frames from Interview model
    if frames is None:
        frames = interview.visual_frames or []
    
    # Limit to 5 frames for cost efficiency
    frames = frames[:5]

    # Get candidate info
    candidate_name = getattr(interview.student, "name", None) or \
                     getattr(interview.student, "first_name", None) or \
                     interview.student.username

    # 3️⃣ Visual feedback analysis
    visual_feedback = None

    if frames and len(frames) > 0:
        print(f"Analyzing {len(frames)} frames for {candidate_name}...")
        
        try:
            from all_services.visual_feedback_service import (
                analyze_frames_aggregated,
                analyze_interview_metadata,
                generate_fallback_feedback
            )
            
            # Clean frames before analysis
            cleaned_frames = []
            for frame in frames:
                frame = frame.strip().replace('\n', '').replace('\r', '').replace(' ', '')
                if not frame.startswith('data:image'):
                    frame = f"data:image/jpeg;base64,{frame.split('base64,')[-1]}"
                cleaned_frames.append(frame)
            
            # Primary: GPT Vision analysis
            visual_feedback = analyze_frames_aggregated(
                frames_b64=cleaned_frames,
                candidate_name=candidate_name,
                candidate_id=interview.student_id
            )
            
            # Check status
            status = visual_feedback.get("status")
            
            if status == "success":
                print(f"Visual analysis successful: {visual_feedback.get('frames_analyzed')} frames")
            
            elif status in ["error", "parse_error", "fallback"]:
                print(f"Visual analysis had issues: {status}")
                
                # Try adding transcript analysis as supplement
                try:
                    print("Adding transcript-based analysis as supplement...")
                    metadata_analysis = analyze_interview_metadata(
                        transcription, 
                        getattr(interview, 'duration_minutes', None)
                    )
                    visual_feedback["communication_analysis"] = metadata_analysis
                    visual_feedback["analysis_type"] = "hybrid"
                except Exception as meta_exc:
                    print(f"Metadata supplement failed: {meta_exc}")
                    
                # If still no good data, use fallback
                if not visual_feedback.get("professional_appearance"):
                    visual_feedback = generate_fallback_feedback(
                        candidate_name, 
                        len(frames)
                    )
            
        except Exception as vf_exc:
            import traceback
            print(f"Visual feedback exception: {vf_exc}")
            print(traceback.format_exc())
            
            # Final fallback
            try:
                from all_services.visual_feedback_service import generate_fallback_feedback
                visual_feedback = generate_fallback_feedback(candidate_name, len(frames))
                visual_feedback["error_occurred"] = str(vf_exc)[:200]
            except Exception:
                visual_feedback = {
                    "status": "critical_error",
                    "message": "Visual feedback unavailable",
                    "frames_captured": len(frames)
                }
    else:
        print("No frames available for visual feedback")
        visual_feedback = {
            "status": "no_frames",
            "message": "No video frames were captured during the interview",
            "note": "Ensure camera permissions are granted and frames are being uploaded",
            "candidate_name": candidate_name
        }

    # 4️⃣ Create the Report
    report = Report.objects.create(
        interview=interview,
        key_strengths=key_strengths,
        areas_for_improvement=areas_for_improvement,
        ratings=ratings,
        visual_feedback=visual_feedback,
    )

    # Update interview status
    if interview.status != "completed":
        interview.status = "completed"
        interview.save(update_fields=["status"])

    print(f"Report created successfully (ID: {report.id})")
    print(f"Visual feedback type: {visual_feedback.get('analysis_type', 'unknown')}")
    
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



# jd parser

class ParseJDAPIView(APIView):
    """
    Upload a JD file and get back parsed text.
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        jd_file = request.FILES.get("jd")
        if not jd_file:
            return Response({"error": "JD file is required (field: jd)"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            jd_text = process_jd_file(jd_file)  # <-- your existing parser
        except Exception as e:
            return Response({"error": f"Failed to parse JD file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"jd_text": jd_text}, status=status.HTTP_200_OK)





# -----------------------------
# Admin-only: Schedule Interview
# -----------------------------
class ScheduleInterviewAPIView(APIView):
    """
    Admin schedules an interview for a student.
    Requires:
      - student (id)
      - jd_text (parsed JD text from ParseJDAPIView)
      - optional: difficulty_level, duration_minutes, scheduled_time
    """
    permission_classes = [IsAdminOrSuperAdmin]

    def post(self, request, *args, **kwargs):
        student_id = request.data.get("student")
        jd_text = request.data.get("jd_text")

        if not student_id:
            return Response({"error": "Student ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        student = get_object_or_404(User, id=student_id, role="student")

        if not jd_text:
            return Response({"error": "jd_text is required. Parse JD first."}, status=status.HTTP_400_BAD_REQUEST)

        difficulty_level = request.data.get("difficulty_level")
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

        scheduled_time = request.data.get("scheduled_time")

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
    Complete interview and generate comprehensive report.
    POST /api/interviews/<interview_id>/complete-and-generate-report/
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, interview_id, *args, **kwargs):
        interview = get_object_or_404(
            Interview.objects.select_related("student"), 
            id=interview_id
        )

        # Permission check
        if not _can_view_or_own(request.user, interview):
            return Response({"error": "Forbidden"}, status=403)

        print(f"Completing interview {interview_id}")
        print(f"Transcript length: {len(interview.full_transcript or '')} chars")
        print(f"Frames available: {len(interview.visual_frames or [])}")

        # Update status if needed
        if interview.status != "completed":
            interview.status = "completed"
            interview.save(update_fields=["status"])

        # Generate report (idempotent - returns existing if already created)
        try:
            report = _create_report_for_interview(interview)
            
            # Check if this was newly created or existing
            from datetime import datetime, timedelta
            created = report.created_at.timestamp() > (datetime.now() - timedelta(seconds=5)).timestamp()
            
        except ValueError as ve:
            # Transcript too short or missing
            print(f"Validation error: {ve}")
            return Response({"error": str(ve)}, status=400)
        except RuntimeError as re:
            # LLM/API failure
            print(f"Runtime error: {re}")
            return Response({"error": str(re)}, status=500)
        except Exception as e:
            # Check if report exists (race condition)
            try:
                report = interview.report
                created = False
                print(f"Report already exists, returning existing report")
            except Report.DoesNotExist:
                import traceback
                print(f"Report creation failed: {e}")
                print(traceback.format_exc())
                return Response(
                    {
                        "error": "Failed to create report",
                        "details": str(e)[:200]
                    }, 
                    status=500
                )

        response_data = ReportSerializer(report).data
        response_data["created"] = created

        print(f"Report {'generated' if created else 'retrieved'} successfully")
        
        return Response(
            response_data, 
            status=201 if created else 200
        )

from .serializers import ReportListSerializer


# class ReportListView(generics.ListAPIView):
#     """
#     Admin: all reports
#     Student: only their reports
#     """
#     serializer_class = ReportListSerializer

#     def get_queryset(self):
#         user = self.request.user
#         qs = Report.objects.select_related("interview", "interview__student")  # join with interview and student

#         if not user.is_authenticated:
#             return Report.objects.none()

#         if getattr(user, "role", None) in ("admin", "super_admin"):
#             return qs.order_by("-created_at")  # Admin sees all reports, ordered by created_at

#         # Only return the reports that belong to the logged-in student
#         return qs.filter(interview__student=user).order_by("-created_at")  # Student only sees their own reports


class ReportListView(generics.ListAPIView):
    """
    Admin: all reports
    Student: only their reports
    Paginated using CursorPagination for performance.
    """
    serializer_class = ReportListSerializer
    pagination_class = ReportCursorPagination  # ✅ production pagination

    def get_queryset(self):
        user = self.request.user
        qs = Report.objects.select_related("interview", "interview__student")

        if not user.is_authenticated:
            return Report.objects.none()

        if getattr(user, "role", None) in ("admin", "super_admin"):
            return qs.order_by("-created_at")

        return qs.filter(interview__student=user).order_by("-created_at")

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

        # 3. Top 3 Centers by Student Count (exclude None/empty/unknown)
        top_centers = (
            User.objects.exclude(center__isnull=True)
                        .exclude(center__exact="")
                        .exclude(center__iexact="unknown")
                        .values("center")
                        .annotate(student_count=Count("id"))
                        .order_by("-student_count")[:3]
        )
        data["top_centers"] = list(top_centers)

        # 4. Daily Interview Count (from Report.created_at)
        daily_counts_qs = (
            Report.objects.annotate(date=TruncDate("created_at"))
                          .values("date")
                          .annotate(count=Count("id"))
                          .order_by("date")
        )

        # Format date as dd-mm-yyyy
        daily_counts = [
            {
                "date": item["date"].strftime("%d-%m-%Y"),
                "count": item["count"]
            }
            for item in daily_counts_qs
        ]

        data["daily_interview_count"] = daily_counts

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




class InterviewTableAPIView(ListAPIView):
    """
    Paginated API for interviews that have reports.
    Returns three sections:
    - interview_table
    - interview_ratings
    - visual_feedback
    """
    permission_classes = [IsAuthenticated]
    pagination_class = ReportCursorPagination

    def get_queryset(self):
        """
        Only include interviews that have a related report.
        """
        return (
            Interview.objects
            .select_related("student", "report")
            .filter(report__isnull=False)
            .order_by("-scheduled_time")
        )

    def list(self, request, *args, **kwargs):
        """
        Paginate queryset and serialize all three sections.
        """
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            # Serialize each section separately
            interview_table = InterviewTableSerializer(page, many=True).data
            interview_ratings = InterviewRatingsSerializer(page, many=True).data
            visual_feedback = VisualFeedbackSerializer(page, many=True).data

            return self.get_paginated_response({
                "interview_table": interview_table,
                "interview_ratings": interview_ratings,
                "visual_feedback": visual_feedback
            })

        # fallback if pagination is not applied (should rarely hit)
        interview_table = InterviewTableSerializer(queryset, many=True).data
        interview_ratings = InterviewRatingsSerializer(queryset, many=True).data
        visual_feedback = VisualFeedbackSerializer(queryset, many=True).data

        return Response({
            "interview_table": interview_table,
            "interview_ratings": interview_ratings,
            "visual_feedback": visual_feedback
        })



class UploadFramesAPIView(APIView):
    """
    Upload video frames during interview for visual feedback analysis.
    POST /api/interviews/<interview_id>/upload-frames/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, interview_id):
        images = request.data.get("images", [])
        if not isinstance(images, list) or not images:
            return Response(
                {"error": "No frames provided"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            interview = Interview.objects.get(id=interview_id, student=request.user)
        except Interview.DoesNotExist:
            return Response(
                {"error": "Interview not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Validate frames
        valid_images = []
        for img in images:
            if isinstance(img, str) and len(img) > 100:
                valid_images.append(img)
        
        if not valid_images:
            return Response(
                {"error": "No valid frames provided"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Store frames in Interview model (append to existing)
        existing_frames = interview.visual_frames or []
        combined_frames = existing_frames + valid_images
        
        # Keep only the most recent 10 frames
        interview.visual_frames = combined_frames[-10:]
        interview.save(update_fields=["visual_frames"])

        print(f"📸 Stored {len(valid_images)} new frames for interview {interview_id}")
        print(f"   Total frames now: {len(interview.visual_frames)}")

        return Response({
            "success": True,
            "frames_stored": len(interview.visual_frames),
            "frames_received": len(valid_images)
        }, status=status.HTTP_200_OK)
        
    


# excel file downlaod

class InterviewExportExcelAPIView(APIView):
    """
    Export all interviews with reports into a single Excel file with
    three sheets: 'interview_table', 'interview_ratings', 'visual_feedback'.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Interview.objects
            .select_related("student", "report")
            # .filter(report__isnull=False)
            .order_by("-scheduled_time")
        )

    def get(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # Serialize each section
        table_data = InterviewTableSerializer(queryset, many=True).data
        ratings_data = InterviewRatingsSerializer(queryset, many=True).data
        visual_data = VisualFeedbackSerializer(queryset, many=True).data

        # Convert serialized JSON-like data to pandas DataFrames.
        # If nested structures exist, you may want to normalize them (see notes below).
        df_table = pd.DataFrame(table_data)
        df_ratings = pd.DataFrame(ratings_data)
        df_visual = pd.DataFrame(visual_data)

        buffer = io.BytesIO()

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df_table.to_excel(writer, sheet_name="interview_table", index=False)
            df_ratings.to_excel(writer, sheet_name="interview_ratings", index=False)
            df_visual.to_excel(writer, sheet_name="visual_feedback", index=False)

        buffer.seek(0)

        filename = f"interviews_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

