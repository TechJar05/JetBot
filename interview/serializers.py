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
