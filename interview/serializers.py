from rest_framework import serializers
from authentication.models import Interview, User
from datetime import timedelta

class InterviewSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)
    student_email = serializers.EmailField(source="student.email", read_only=True)

    class Meta:
        model = Interview
        fields = [
            "id",
            "student",   # student_id (FK)
            "student_name",
            "student_email",
            "jd",
            "difficulty_level",
            "scheduled_time",
            "duration_minutes",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]
