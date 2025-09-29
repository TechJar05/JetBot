from django.db import models

# Create your models here.
from django.db import models
from authentication.models import User  # FK → user.id

class Interview(models.Model):
    DIFFICULTY_CHOICES = (
        ("beginner", "Beginner"),
        ("medium", "Medium"),
        ("advanced", "Advanced"),
    )

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
    )

    id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="interviews"
    )
    jd = models.TextField()  # Job description
    difficulty_level = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="beginner"
    )
    scheduled_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Interview {self.id} - {self.student.email}"
