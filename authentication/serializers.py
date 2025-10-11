# users/serializers.py
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from authentication.models import *



from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import User

class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    courseName = serializers.CharField(source='course_name')
    mobileNumber = serializers.CharField(source='mobile_no')
    batchNo = serializers.CharField(source='batch_no')

    class Meta:
        model = User
        fields = ('name', 'courseName', 'email', 'mobileNumber', 'center', 'batchNo', 'password', 'role')

    def validate_mobileNumber(self, value):
        """Check if mobile number already exists."""
        if User.objects.filter(mobile_no=value).exists():
            raise serializers.ValidationError("This mobile number is already registered.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES)




from rest_framework import serializers

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=6)
