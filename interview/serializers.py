from rest_framework import serializers
from authentication.models import Interview, User


class InterviewSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)
    student_email = serializers.EmailField(source="student.email", read_only=True)

    class Meta:
        model = Interview
        fields = [
            "id",
            "student",         # FK: student_id
            "student_name",    # derived
            "student_email",   # derived
            "jd",
            "difficulty_level",
            "scheduled_time",
            "duration_minutes",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]

    def validate_difficulty_level(self, value):
        """Ensure difficulty_level is one of the valid choices."""
        valid_choices = [choice[0] for choice in Interview.DIFFICULTY_CHOICES]
        if value not in valid_choices:
            raise serializers.ValidationError(
                f"Invalid difficulty level. Choose one of: {', '.join(valid_choices)}"
            )
        return value


class StudentSearchSerializer(serializers.ModelSerializer):
    """Lightweight serializer for student search (autocomplete)."""

    class Meta:
        model = User
        fields = ["id", "name", "email"]
        
from rest_framework import serializers
from authentication.models import Report


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = "__all__"
        read_only_fields = ("id", "created_at", "interview")


from rest_framework import serializers
from authentication.models import Report

class ReportListSerializer(serializers.ModelSerializer):
    report_id = serializers.IntegerField(source="id")  # report ID from Report model
    student_name = serializers.CharField(source="interview.student.name")
    roll_no = serializers.CharField(source="interview.student.batch_no")
    batch_no = serializers.CharField(source="interview.student.batch_no")
    center = serializers.CharField(source="interview.student.center")
    course = serializers.CharField(source="interview.student.course_name")
    evaluation_date = serializers.DateTimeField(source="interview.scheduled_time")
    difficulty_level = serializers.CharField(source="interview.difficulty_level")
    interview_time = serializers.DateTimeField(source="interview.scheduled_time")

    class Meta:
        model = Report
        fields = [
            "report_id",  # The report's ID
            "student_name",
            "roll_no",
            "batch_no",
            "center",
            "course",
            "evaluation_date",
            "difficulty_level",
            "interview_time",
        ]




#  student dashboard analytic report
class StudentAnalyticsSerializer(serializers.Serializer):
    total_average_rating = serializers.FloatField()
    completed_interviews = serializers.IntegerField()
    skill_breakdown = serializers.DictField()
    interview_ratings = serializers.ListField()
    


#  recuirter dashboard tables serilizers:
from rest_framework import serializers
from authentication.models import User, Interview, Report

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


class InterviewRatingsSerializer(serializers.ModelSerializer):
    mail_id = serializers.EmailField(source="student.email")
    technical_rating = serializers.IntegerField(source="report.ratings.technical")
    communication_rating = serializers.IntegerField(source="report.ratings.communication")
    problem_solving_rating = serializers.IntegerField(source="report.ratings.problem_solving")
    time_management_rating = serializers.IntegerField(source="report.ratings.time_mgmt")
    total_rating = serializers.IntegerField(source="report.ratings.total")
    interview_ts = serializers.DateTimeField(source="scheduled_time")

    class Meta:
        model = Interview
        fields = [
            "mail_id", "technical_rating", "communication_rating",
            "problem_solving_rating", "time_management_rating",
            "total_rating", "interview_ts"
        ]


class VisualFeedbackSerializer(serializers.ModelSerializer):
    roll_no = serializers.CharField(source="student.id")
    professional_appearance = serializers.SerializerMethodField()
    body_language = serializers.SerializerMethodField()
    environment = serializers.SerializerMethodField()
    distractions = serializers.SerializerMethodField()
    interview_ts = serializers.DateTimeField(source="scheduled_time")

    class Meta:
        model = Interview
        fields = [
            "roll_no", "professional_appearance", "body_language",
            "environment", "distractions", "interview_ts"
        ]

    def get_professional_appearance(self, obj):
        try:
            if obj.report and obj.report.visual_feedback:
                return obj.report.visual_feedback[0].get("appearance", "")
        except Report.DoesNotExist:
            return ""
        return ""

    def get_body_language(self, obj):
        try:
            if obj.report and obj.report.visual_feedback:
                return obj.report.visual_feedback[0].get("body_language", "")
        except Report.DoesNotExist:
            return ""
        return ""

    def get_environment(self, obj):
        try:
            if obj.report and obj.report.visual_feedback:
                return obj.report.visual_feedback[0].get("environment", "")
        except Report.DoesNotExist:
            return ""
        return ""

    def get_distractions(self, obj):
        try:
            if obj.report and obj.report.visual_feedback:
                return obj.report.visual_feedback[0].get("distractions", "")
        except Report.DoesNotExist:
            return ""
        return ""



