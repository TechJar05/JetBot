# serializers.py
from rest_framework import serializers
from authentication.models import Interview, User, Report


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
    evaluation_date = serializers.DateTimeField(source="created_at")
    jd_id = serializers.IntegerField(source="id")

    class Meta:
        model = Interview
        fields = [
            "student_name", "roll_no", "batch_no", "center", "course",
            "evaluation_date", "difficulty_level", "jd_id", "status", "scheduled_time"
        ]


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
    scheduled_time = serializers.DateTimeField(source="interview.scheduled_time", read_only=True)
    
    # Computed fields
    avg_key_strength_rating = serializers.SerializerMethodField()
    visual_frames_count = serializers.SerializerMethodField()  # NEW
    has_visual_feedback = serializers.SerializerMethodField()  # NEW

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
            "scheduled_time",
            # Computed fields
            "avg_key_strength_rating",
            "visual_frames_count",
            "has_visual_feedback",
        ]
        read_only_fields = ("id", "created_at", "interview")

    def get_avg_key_strength_rating(self, obj):
        """Compute average rating from key_strengths JSON field"""
        try:
            strengths = obj.key_strengths or []
            ratings = [
                s.get("rating")
                for s in strengths
                if isinstance(s.get("rating"), (int, float))
            ]
            if ratings:
                return round(sum(ratings) / len(ratings), 2)
        except Exception:
            return None
        return None

    def get_visual_frames_count(self, obj):
        """Get frame count from Interview model"""
        try:
            return len(obj.interview.visual_frames or [])
        except Exception:
            return 0

    def get_has_visual_feedback(self, obj):
        """Check if visual feedback was generated"""
        if not obj.visual_feedback:
            return False
        status = obj.visual_feedback.get("status")
        return status in ["success", "fallback", "hybrid"]


class ReportListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for report listings"""

    report_id = serializers.IntegerField(source="id")
    student_name = serializers.CharField(source="interview.student.name")
    roll_no = serializers.CharField(source="interview.student.batch_no")
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

    # --- Format: dd/mm/yyyy ---
    def get_evaluation_date(self, obj):
        date = obj.interview.scheduled_time
        return date.strftime("%d/%m/%Y") if date else None

    # --- Time of report creation ---
    def get_interview_time(self, obj):
        time = obj.created_at  # report creation time
        return time.strftime("%H:%M:%S") if time else None

# ============================================
# VISUAL FEEDBACK SERIALIZER (FIXED)
# ============================================

class VisualFeedbackSerializer(serializers.ModelSerializer):
    """
    Serializer for visual feedback data.
    Now properly handles visual_feedback from Report model.
    """
    roll_no = serializers.CharField(source="student.id")
    interview_ts = serializers.DateTimeField(source="scheduled_time")
    
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

    def _get_visual_feedback(self, obj):
        """Get visual_feedback dict from Report"""
        try:
            report = obj.report  # Access related Report
            return report.visual_feedback if report else {}
        except Report.DoesNotExist:
            return {}

    def _get_feedback_field(self, obj, key, default="Not available"):
        """Safely extract a field from visual_feedback JSON"""
        feedback = self._get_visual_feedback(obj)
        if not feedback:
            return default
        
        # Handle different status cases
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
# INTERVIEW RATINGS SERIALIZER (FIXED)
# ============================================

class InterviewRatingsSerializer(serializers.ModelSerializer):
    """Serializer for interview ratings table"""
    mail_id = serializers.EmailField(source="student.email")
    interview_ts = serializers.DateTimeField(source="scheduled_time")
    
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