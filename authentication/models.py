from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
 
 
# --------------------------
# User Manager
# --------------------------
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, role="student", **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
 
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", "super_admin")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)
 
 
# --------------------------
# User Model
# --------------------------
class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ("student", "Student"),
        ("admin", "Admin"),
        ("super_admin", "Super Admin"),
    )
 
    id = models.AutoField(primary_key=True)
    email = models.EmailField(unique=True, max_length=255)
    password = models.CharField(max_length=255)  # hashed password
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    
    # Extra student-specific fields (nullable for admins)
    name = models.CharField(max_length=150, null=True, blank=True)
    course_name = models.CharField(max_length=150, null=True, blank=True)
    mobile_no = models.CharField(max_length=20, null=True, blank=True, unique=True)
    center = models.CharField(max_length=100, null=True, blank=True)
    batch_no = models.CharField(max_length=50, null=True, blank=True)
 
    created_at = models.DateTimeField(auto_now_add=True)
 
    # Django admin integration
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
 
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
 
    objects = UserManager()
 
    def __str__(self):
        return f"{self.email} ({self.role})"
 
 
# --------------------------
# Interview Model
# --------------------------
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
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="interviews")
    jd = models.TextField()
    difficulty_level = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES)
    scheduled_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    full_transcript = models.TextField(null=True, blank=True)
    visual_frames = models.JSONField(null=True, blank=True) 
    questions = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
 
    def __str__(self):
        return f"Interview {self.id} - {self.student.email}"
 
 
# --------------------------
# Report Model
# --------------------------
class Report(models.Model):
    id = models.AutoField(primary_key=True)
    interview = models.OneToOneField(Interview, on_delete=models.CASCADE, related_name="report")
    key_strengths = models.JSONField(null=True, blank=True)  # [{"area": "DSA", "example": "...", "rating": 4}]
    areas_for_improvement = models.JSONField(null=True, blank=True)  # [{"area": "Comm", "suggestions": "..."}]
    visual_feedback = models.JSONField(null=True, blank=True)  # [{"appearance": "Formal", "eye_contact": "Good"}]
    ratings = models.JSONField(null=True, blank=True)  # {"technical":4,"communication":3,"problem_solving":4,"time_mgmt":3,"total":14}
    detailed_evaluation = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
 
    def __str__(self):
        return f"Report for Interview {self.interview.id}"
 
 
# --------------------------
# Analytics Export (Tracking sync with Snowflake)
# --------------------------
class AnalyticsExport(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    )
 
    id = models.AutoField(primary_key=True)
    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name="exports")
    exported_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
 
    def __str__(self):
        return f"Export {self.id} for Interview {self.interview.id}"



from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import datetime

User = get_user_model()

class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_otps")
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)

    def is_expired(self):
        return self.created_at + datetime.timedelta(minutes=10) < timezone.now()

    def __str__(self):
        return f"OTP {self.otp} for {self.user.email}"
