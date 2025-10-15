# serializers.py
from rest_framework import serializers
from authentication.models import Interview, User, Report
from django.utils import timezone
import pytz



# ============================================
# INTERVIEW SERIALIZERS
# ============================================

class InterviewSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)
    student_email = serializers.EmailField(source="student.email", read_only=True)
    student_batch = serializers.CharField(source="student.batch_no", read_only=True)
    student_center = serializers.CharField(source="student.center", read_only=True)
    student_course = serializers.CharField(source="student.course_name", read_only=True)
    frames_count = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = [
            "id",
            "student",
            "student_name",
            "student_email",
            "student_batch",
            "student_center",
            "student_course",
            "jd",
            "difficulty_level",
            "scheduled_time",
            "duration_minutes",
            "status",
            "created_at",
            "frames_count",  # NEW: show how many frames captured
        ]
        read_only_fields = ["id", "status", "created_at"]

    def validate_difficulty_level(self, value):
        valid_choices = [choice[0] for choice in Interview.DIFFICULTY_CHOICES]
        if value not in valid_choices:
            raise serializers.ValidationError(
                f"Invalid difficulty level. Choose one of: {', '.join(valid_choices)}"
            )
        return value

    def get_frames_count(self, obj):
        """Return count of captured video frames"""
        return len(obj.visual_frames or [])


class InterviewTableSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name")
    roll_no = serializers.CharField(source="student.id")
    batch_no = serializers.CharField(source="student.batch_no")
    center = serializers.CharField(source="student.center")
    course = serializers.CharField(source="student.course_name")

    evaluation_date = serializers.SerializerMethodField()
    interview_ts = serializers.SerializerMethodField()  # NEW FIELD
    jd_id = serializers.IntegerField(source="id")

    class Meta:
        model = Interview
        fields = [
            "student_name",
            "roll_no",
            "batch_no",
            "center",
            "course",
            "evaluation_date",
            "interview_ts",   # Added here
            "difficulty_level",
            "jd_id",
            "status",
        ]

    # --- Convert evaluation_date (Interview.created_at) to IST readable format ---
    def get_evaluation_date(self, obj):
        dt = obj.created_at
        if not dt:
            return None
        ist = pytz.timezone("Asia/Kolkata")
        local_dt = timezone.localtime(dt, ist)
        return local_dt.strftime("%A, %d/%m/%Y %H:%M:%S")

    # --- Add interview_time from related Report (Report.created_at) ---
    def get_interview_ts(self, obj):
        try:
            report = obj.report  # one-to-one relation (Interview -> Report)
            if not report or not report.created_at:
                return None
            ist = pytz.timezone("Asia/Kolkata")
            local_dt = timezone.localtime(report.created_at, ist)
            return local_dt.strftime("%A, %d/%m/%Y %H:%M:%S")
        except Exception:
            return None


# ============================================
# INTERVIEW RATINGS SERIALIZER (FIXED)
# ============================================

class InterviewRatingsSerializer(serializers.ModelSerializer):
    """Serializer for interview ratings table"""
    mail_id = serializers.EmailField(source="student.email")

    # Replaced scheduled_time with report.created_at in IST readable format
    interview_ts = serializers.SerializerMethodField()

    # Ratings from Report
    technical_rating = serializers.SerializerMethodField()
    communication_rating = serializers.SerializerMethodField()
    problem_solving_rating = serializers.SerializerMethodField()
    time_management_rating = serializers.SerializerMethodField()
    total_rating = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = [
            "mail_id",
            "technical_rating",
            "communication_rating",
            "problem_solving_rating",
            "time_management_rating",
            "total_rating",
            "interview_ts",
        ]

    # ✅ Format interview timestamp from Report.created_at
    def get_interview_ts(self, obj):
        try:
            report = obj.report  # one-to-one relation (Interview -> Report)
            if not report or not report.created_at:
                return None
            ist = pytz.timezone("Asia/Kolkata")
            local_dt = timezone.localtime(report.created_at, ist)
            return local_dt.strftime("%A, %d/%m/%Y %H:%M:%S")
        except Report.DoesNotExist:
            return None

    # --- Safely get ratings from Report JSON field ---
    def _get_rating(self, obj, key, default=0):
        """Safely get rating from Report.ratings JSON field"""
        try:
            report = obj.report
            ratings = report.ratings or {}
            return ratings.get(key, default)
        except Report.DoesNotExist:
            return default

    def get_technical_rating(self, obj):
        return self._get_rating(obj, "technical")

    def get_communication_rating(self, obj):
        return self._get_rating(obj, "communication")

    def get_problem_solving_rating(self, obj):
        return self._get_rating(obj, "problem_solving")

    def get_time_management_rating(self, obj):
        return self._get_rating(obj, "time_mgmt")

    def get_total_rating(self, obj):
        return self._get_rating(obj, "total")
    
    
    
# ============================================
# REPORT SERIALIZERS
# ============================================

class ReportSerializer(serializers.ModelSerializer):
    """Main report serializer with all details"""

    student_id = serializers.IntegerField(source="interview.student.id", read_only=True)
    student_name = serializers.CharField(source="interview.student.name", read_only=True)
    student_email = serializers.EmailField(source="interview.student.email", read_only=True)
    student_batch = serializers.CharField(source="interview.student.batch_no", read_only=True)
    student_center = serializers.CharField(source="interview.student.center", read_only=True)
    student_course = serializers.CharField(source="interview.student.course_name", read_only=True)

    difficulty_level = serializers.CharField(source="interview.difficulty_level", read_only=True)

    scheduled_time = serializers.SerializerMethodField()
    interview_time = serializers.SerializerMethodField()

    # Computed fields
    avg_rating = serializers.SerializerMethodField()  # ✅ renamed to reflect actual data
    visual_frames_count = serializers.SerializerMethodField()
    has_visual_feedback = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "interview",
            "key_strengths",
            "areas_for_improvement",
            "ratings",
            "visual_feedback",
            "created_at",
            # Student info
            "student_id",
            "student_name",
            "student_email",
            "student_batch",
            "student_center",
            "student_course",
            "difficulty_level",
            # Time fields
            "scheduled_time",
            "interview_time",
            # Computed fields
            "avg_rating",
            "visual_frames_count",
            "has_visual_feedback",
        ]
        read_only_fields = ("id", "created_at", "interview")

    # --- Format scheduled_time (Day + Date + Time in IST) ---
    def get_scheduled_time(self, obj):
        dt = obj.interview.scheduled_time
        if not dt:
            return None
        ist = pytz.timezone("Asia/Kolkata")
        local_dt = timezone.localtime(dt, ist)
        return local_dt.strftime("%A, %d/%m/%Y %H:%M:%S")

    # --- Add interview_time from report creation (Day + Date + Time in IST) ---
    def get_interview_time(self, obj):
        created = obj.created_at
        if not created:
            return None
        ist = pytz.timezone("Asia/Kolkata")
        local_time = timezone.localtime(created, ist)
        return local_time.strftime("%A, %d/%m/%Y %H:%M:%S")

    # ✅ NEW — Calculate average rating from ratings JSON (dict type)
    def get_avg_rating(self, obj):
        """Compute average rating from ratings JSON field"""
        try:
            ratings_data = obj.ratings or {}
            
            # Extract all ratings except 'total'
            ratings = [
                value
                for key, value in ratings_data.items()
                if key != "total" and isinstance(value, (int, float))
            ]
            
            if ratings:
                return round(sum(ratings) / len(ratings), 2)
        except Exception:
            return None
        return None

    def get_visual_frames_count(self, obj):
        """Count total visual frames if present"""
        frames = obj.interview.visual_frames or []
        return len(frames)

    def get_has_visual_feedback(self, obj):
        """Check if visual feedback exists"""
        return bool(obj.visual_feedback)


class ReportListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for report listings"""

    report_id = serializers.IntegerField(source="id")
    student_name = serializers.CharField(source="interview.student.name")
    roll_no = serializers.IntegerField(source="interview.student.id", read_only=True)
    batch_no = serializers.CharField(source="interview.student.batch_no")
    center = serializers.CharField(source="interview.student.center")
    course = serializers.CharField(source="interview.student.course_name")

    # Custom formatted fields
    evaluation_date = serializers.SerializerMethodField()
    interview_time = serializers.SerializerMethodField()
    difficulty_level = serializers.CharField(source="interview.difficulty_level")

    class Meta:
        model = Report
        fields = [
            "report_id",
            "student_name",
            "roll_no",
            "batch_no",
            "center",
            "course",
            "evaluation_date",
            "difficulty_level",
            "interview_time",
        ]

    def get_evaluation_date(self, obj):
        """Day + Date + Time (IST) of the interview schedule"""
        date = obj.interview.scheduled_time
        if not date:
            return None
        ist = pytz.timezone("Asia/Kolkata")
        local_date = timezone.localtime(date, ist)
        return local_date.strftime("%A, %d/%m/%Y %H:%M:%S")

    def get_interview_time(self, obj):
        """Day + Date + Time (IST) when report was created"""
        time = obj.created_at
        if not time:
            return None
        ist = pytz.timezone("Asia/Kolkata")
        local_time = timezone.localtime(time, ist)
        return local_time.strftime("%A, %d/%m/%Y %H:%M:%S") 
    
    
# ============================================
# VISUAL FEEDBACK SERIALIZER (FIXED)
# ============================================

class VisualFeedbackSerializer(serializers.ModelSerializer):
    """
    Serializer for visual feedback data.
    Handles visual_feedback from Report model and formats interview timestamp.
    """
    roll_no = serializers.CharField(source="student.id")
    interview_ts = serializers.SerializerMethodField()  # From report.created_at

    # Visual feedback fields
    professional_appearance = serializers.SerializerMethodField()
    body_language = serializers.SerializerMethodField()
    facial_expressions = serializers.SerializerMethodField()
    environment = serializers.SerializerMethodField()
    distractions = serializers.SerializerMethodField()
    
    # Metadata
    analysis_type = serializers.SerializerMethodField()
    frames_analyzed = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = [
            "roll_no",
            "interview_ts",
            "professional_appearance",
            "body_language",
            "facial_expressions",
            "environment",
            "distractions",
            "analysis_type",
            "frames_analyzed",
        ]

    # --- Get interview timestamp from Report.created_at in IST format ---
    def get_interview_ts(self, obj):
        try:
            report = obj.report
            if not report or not report.created_at:
                return None
            ist = pytz.timezone("Asia/Kolkata")
            local_dt = timezone.localtime(report.created_at, ist)
            return local_dt.strftime("%A, %d/%m/%Y %H:%M:%S")
        except Report.DoesNotExist:
            return None

    # --- Visual feedback helpers ---
    def _get_visual_feedback(self, obj):
        """Get visual_feedback dict from Report"""
        try:
            report = obj.report
            return report.visual_feedback if report else {}
        except Report.DoesNotExist:
            return {}

    def _get_feedback_field(self, obj, key, default="Not available"):
        """Safely extract a field from visual_feedback JSON"""
        feedback = self._get_visual_feedback(obj)
        if not feedback:
            return default

        status = feedback.get("status")
        if status in ["error", "no_frames", "critical_error"]:
            return feedback.get("message", default)

        return feedback.get(key, default)

    def get_professional_appearance(self, obj):
        return self._get_feedback_field(obj, "professional_appearance")

    def get_body_language(self, obj):
        return self._get_feedback_field(obj, "body_language")

    def get_facial_expressions(self, obj):
        return self._get_feedback_field(obj, "facial_expressions")

    def get_environment(self, obj):
        return self._get_feedback_field(obj, "environment")

    def get_distractions(self, obj):
        return self._get_feedback_field(obj, "distractions")

    def get_analysis_type(self, obj):
        feedback = self._get_visual_feedback(obj)
        return feedback.get("analysis_type", "none")

    def get_frames_analyzed(self, obj):
        """Get number of frames that were analyzed"""
        feedback = self._get_visual_feedback(obj)
        if feedback:
            return feedback.get("frames_analyzed", len(obj.visual_frames or []))
        return len(obj.visual_frames or [])



# ============================================
# ANALYTICS SERIALIZERS
# ============================================

class StudentAnalyticsSerializer(serializers.Serializer):
    """Analytics data for student dashboard"""
    total_average_rating = serializers.FloatField()
    completed_interviews = serializers.IntegerField()
    skill_breakdown = serializers.DictField()
    interview_ratings = serializers.ListField()


class StudentSearchSerializer(serializers.ModelSerializer):
    """Lightweight serializer for student search (autocomplete)"""
    class Meta:
        model = User
        fields = ["id", "name", "email"]