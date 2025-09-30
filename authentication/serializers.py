# users/serializers.py
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from authentication.models import *




class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    courseName = serializers.CharField(source='course_name')
    mobileNumber = serializers.CharField(source='mobile_no')
    batchNo = serializers.CharField(source='batch_no')

    class Meta:
        model = User
        fields = ('name', 'courseName', 'email', 'mobileNumber', 'center', 'batchNo', 'password', 'role')

    def create(self, validated_data):
        user = User(
            email=validated_data['email'],
            name=validated_data.get('name'),
            course_name=validated_data.get('course_name'),
            mobile_no=validated_data.get('mobile_no'),
            center=validated_data.get('center'),
            batch_no=validated_data.get('batch_no'),
            role=validated_data.get('role', 'student')
        )
        user.set_password(validated_data['password'])
        user.save()
        return user


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
