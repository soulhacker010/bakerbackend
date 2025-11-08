from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .email_feedback import FeedbackEmail, FeedbackEmailError, send_feedback_email
from .email_two_factor import TwoFactorEmail, TwoFactorEmailError, send_two_factor_email
from .models import TwoFactorChallenge
from .serializers import (
    FeedbackSubmissionSerializer,
    LoginSerializer,
    ProfileSerializer,
    SignupSerializer,
    TwoFactorResendSerializer,
    TwoFactorVerifySerializer,
    UserSerializer,
)
from .two_factor import (
    create_two_factor_challenge,
    regenerate_two_factor_challenge,
    verify_two_factor_code,
)


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = (permissions.AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        headers = self.get_success_headers(serializer.data)
        return Response({"user": UserSerializer(user).data, "token": token.key}, status=status.HTTP_201_CREATED, headers=headers)


class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        if not user.two_factor_enabled:
            token, _ = Token.objects.get_or_create(user=user)
            return Response({"user": UserSerializer(user).data, "token": token.key}, status=status.HTTP_200_OK)

        challenge, code = create_two_factor_challenge(user)

        recipient_name = f"{user.first_name} {user.last_name}".strip() or user.email

        try:
            send_two_factor_email(
                TwoFactorEmail(
                    recipient=user.email,
                    recipient_name=recipient_name,
                    code=code,
                )
            )
        except TwoFactorEmailError as exc:
            challenge.delete()
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        payload = {
            "detail": "verification_required",
            "challengeId": str(challenge.challenge_id),
            "expiresAt": challenge.expires_at.astimezone(dt_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "resendAvailableIn": settings.TWO_FACTOR_RESEND_INTERVAL_SECONDS,
            "ttlSeconds": settings.TWO_FACTOR_CODE_TTL_MINUTES * 60,
        }
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user


class FeedbackSubmissionView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = FeedbackSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        feedback_type = serializer.validated_data["type"]
        message = serializer.validated_data["message"]
        user = request.user

        author_name = f"{user.first_name} {user.last_name}".strip()
        if not author_name:
            author_name = user.email

        email_payload = FeedbackEmail(
            author_email=user.email,
            author_name=author_name,
            feedback_type=feedback_type,
            message=message,
        )

        try:
            send_feedback_email(email_payload)
        except FeedbackEmailError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({"detail": "Feedback submitted. Thank you!"}, status=status.HTTP_202_ACCEPTED)


class TwoFactorVerifyView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = TwoFactorVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challenge = TwoFactorChallenge.objects.select_related("user").filter(
            challenge_id=serializer.validated_data["challenge_id"]
        ).first()

        if not challenge:
            return Response({"detail": "Invalid or expired verification challenge."}, status=status.HTTP_400_BAD_REQUEST)

        user = challenge.user
        now = timezone.now()

        if challenge.expires_at <= now:
            challenge.delete()
            return Response({"detail": "Verification code expired."}, status=status.HTTP_400_BAD_REQUEST)

        if not user.two_factor_enabled:
            challenge.delete()
            token, _ = Token.objects.get_or_create(user=user)
            return Response({"user": UserSerializer(user).data, "token": token.key}, status=status.HTTP_200_OK)

        if challenge.attempts >= settings.TWO_FACTOR_MAX_ATTEMPTS:
            challenge.delete()
            return Response({"detail": "Maximum verification attempts exceeded."}, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data["code"]

        if not verify_two_factor_code(challenge, code):
            challenge.attempts += 1
            challenge.save(update_fields=["attempts", "updated_at"])
            remaining = max(settings.TWO_FACTOR_MAX_ATTEMPTS - challenge.attempts, 0)
            return Response(
                {
                    "detail": "Incorrect verification code.",
                    "attemptsRemaining": remaining,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        challenge.delete()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"user": UserSerializer(user).data, "token": token.key}, status=status.HTTP_200_OK)


class TwoFactorResendView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = TwoFactorResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        challenge = TwoFactorChallenge.objects.select_related("user").filter(
            challenge_id=serializer.validated_data["challenge_id"]
        ).first()

        if not challenge:
            return Response({"detail": "Invalid or expired verification challenge."}, status=status.HTTP_400_BAD_REQUEST)

        user = challenge.user
        now = timezone.now()

        if challenge.expires_at <= now:
            challenge.delete()
            return Response({"detail": "Verification code expired."}, status=status.HTTP_400_BAD_REQUEST)

        if not user.two_factor_enabled:
            challenge.delete()
            return Response({"detail": "Two-factor authentication is no longer required."}, status=status.HTTP_400_BAD_REQUEST)

        seconds_since_last = (now - challenge.last_sent_at).total_seconds()
        if seconds_since_last < settings.TWO_FACTOR_RESEND_INTERVAL_SECONDS:
            retry_after = settings.TWO_FACTOR_RESEND_INTERVAL_SECONDS - int(seconds_since_last)
            return Response(
                {
                    "detail": "Please wait before requesting another code.",
                    "retryAfter": retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            code = regenerate_two_factor_challenge(challenge)
            recipient_name = f"{user.first_name} {user.last_name}".strip() or user.email
            send_two_factor_email(
                TwoFactorEmail(
                    recipient=user.email,
                    recipient_name=recipient_name,
                    code=code,
                )
            )
        except TwoFactorEmailError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        payload = {
            "detail": "verification_required",
            "challengeId": str(challenge.challenge_id),
            "expiresAt": challenge.expires_at.astimezone(dt_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "resendAvailableIn": settings.TWO_FACTOR_RESEND_INTERVAL_SECONDS,
            "ttlSeconds": settings.TWO_FACTOR_CODE_TTL_MINUTES * 60,
        }
        return Response(payload, status=status.HTTP_202_ACCEPTED)
