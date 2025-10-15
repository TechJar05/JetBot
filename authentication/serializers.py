# users/serializers.py
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from authentication.models import *
from .models import User



class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])

    # Map camelCase input to model field names
    courseName = serializers.CharField(source='course_name', required=False, allow_blank=True)
    mobileNumber = serializers.CharField(source='mobile_no', required=False, allow_blank=True)
    batchNo = serializers.CharField(source='batch_no', required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('name', 'courseName', 'email', 'mobileNumber', 'center', 'batchNo', 'password', 'role')

    def validate_mobileNumber(self, value):
        """Check if mobile number already exists."""
        if value and User.objects.filter(mobile_no=value).exists():
            raise serializers.ValidationError("This mobile number is already registered.")
        return value

    def validate_email(self, value):
        """Check if email already exists."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("This email is already registered.")
        return value

    def create(self, validated_data):
        """Use create_user from UserManager for proper password hashing."""
        password = validated_data.pop('password')

        # Flatten nested fields (from source mappings)
        course_name = validated_data.pop('course_name', None)
        mobile_no = validated_data.pop('mobile_no', None)
        batch_no = validated_data.pop('batch_no', None)

        user = User.objects.create_user(
            password=password,
            course_name=course_name,
            mobile_no=mobile_no,
            batch_no=batch_no,
            **validated_data
        )
        return user



class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES)



class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=6)
