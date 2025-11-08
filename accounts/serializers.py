from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import PasswordResetToken, User


PROFILE_FIELDS = (
    "id",
    "email",
    "first_name",
    "last_name",
    "title",
    "profession",
    "practice_name",
    "country",
    "two_factor_enabled",
    "notify_admin",
    "notify_practitioner",
    "results_delivery_format",
    "results_copy_email",
    "reply_mode",
    "reply_email",
    "redirect_link",
    "date_joined",
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = PROFILE_FIELDS
        read_only_fields = ("id", "email", "date_joined")


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("email", "password", "first_name", "last_name", "profession")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        return user


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = PROFILE_FIELDS
        read_only_fields = ("id", "email", "date_joined")


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(self.context.get("request"), email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        attrs["user"] = user
        return attrs


class FeedbackSubmissionSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=("general", "error", "feature", "other"))
    message = serializers.CharField(max_length=4000, trim_whitespace=True)

    def validate_message(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Message cannot be blank.")
        return cleaned


class TwoFactorVerifySerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    code = serializers.CharField(max_length=10, trim_whitespace=True)

    def validate_code(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit():
            raise serializers.ValidationError("Verification code must contain only digits.")
        return cleaned


class TwoFactorResendSerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetValidateSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    signature = serializers.CharField(max_length=512)

    def validate(self, attrs):
        token_id = attrs["token"]
        raw_token = attrs["signature"]

        token = PasswordResetToken.objects.filter(token_id=token_id).select_related("user").first()
        if not token:
            raise serializers.ValidationError("Invalid or expired reset link.")

        from .password_reset import verify_password_reset_token

        if not verify_password_reset_token(token, raw_token):
            raise serializers.ValidationError("Invalid or expired reset link.")

        attrs["token_obj"] = token
        attrs["user"] = token.user
        attrs["raw_token"] = raw_token
        return attrs


class PasswordResetCompleteSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    signature = serializers.CharField(max_length=512)
    password = serializers.CharField(min_length=8, write_only=True)

    def validate(self, attrs):
        token_id = attrs["token"]
        raw_token = attrs["signature"]

        token = PasswordResetToken.objects.filter(token_id=token_id).select_related("user").first()
        if not token:
            raise serializers.ValidationError("Invalid or expired reset link.")

        from .password_reset import verify_password_reset_token

        if not verify_password_reset_token(token, raw_token):
            raise serializers.ValidationError("Invalid or expired reset link.")

        attrs["token_obj"] = token
        attrs["user"] = token.user
        attrs["raw_token"] = raw_token
        return attrs
