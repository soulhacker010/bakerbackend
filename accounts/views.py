from datetime import datetime, timezone as dt_timezone
from typing import Optional

from django.conf import settings
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .email_feedback import FeedbackEmail, FeedbackEmailError, send_feedback_email
from .email_password_reset import PasswordResetEmail, PasswordResetEmailError, send_password_reset_email
from .email_two_factor import TwoFactorEmail, TwoFactorEmailError, send_two_factor_email
from .models import PasswordResetToken, TwoFactorChallenge, User
from .serializers import (
    FeedbackSubmissionSerializer,
    LoginSerializer,
    PasswordResetCompleteSerializer,
    PasswordResetRequestSerializer,
    PasswordResetValidateSerializer,
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
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .password_reset import invalidate_password_reset_tokens, issue_password_reset_token
from .turnstile import (
    TurnstileServiceError,
    TurnstileValidationError,
    validate_turnstile_token,
)


def _get_client_ip(request) -> Optional[str]:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _validate_turnstile_or_response(request, token: Optional[str]):
    try:
        validate_turnstile_token(token, remote_ip=_get_client_ip(request))
    except TurnstileValidationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except TurnstileServiceError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return None


def _format_timestamp(exp_timestamp: int) -> str:
    return (
        datetime.fromtimestamp(exp_timestamp, tz=dt_timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _issue_jwt_pair(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    access_token = refresh.access_token
    return {
        "access": str(access_token),
        "refresh": str(refresh),
        "access_expires_at": _format_timestamp(int(access_token["exp"])),
        "refresh_expires_at": _format_timestamp(int(refresh["exp"])),
    }


def _build_auth_payload(user: User) -> dict:
    tokens = _issue_jwt_pair(user)
    return {
        "user": UserSerializer(user).data,
        "access": tokens["access"],
        "refresh": tokens["refresh"],
        "accessExpiresAt": tokens["access_expires_at"],
        "refreshExpiresAt": tokens["refresh_expires_at"],
    }


def _blacklist_user_tokens(user: User) -> None:
    try:
        from rest_framework_simplejwt.token_blacklist import models as blacklist_models
    except ImportError:  # pragma: no cover - optional blacklist app
        return

    outstanding = blacklist_models.OutstandingToken.objects.filter(user=user)
    for token in outstanding:
        blacklist_models.BlacklistedToken.objects.get_or_create(token=token)


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = (permissions.AllowAny,)

    def initial(self, request, *args, **kwargs):  # pragma: no cover - guard clause
        super().initial(request, *args, **kwargs)
        if not getattr(settings, "SIGNUP_ENABLED", False):
            raise PermissionDenied("Self-service signup is disabled.")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        error_response = _validate_turnstile_or_response(request, serializer.validated_data.get("turnstile_token"))
        if error_response is not None:
            return error_response
        user = serializer.save()
        headers = self.get_success_headers(serializer.data)
        payload = _build_auth_payload(user)
        return Response(payload, status=status.HTTP_201_CREATED, headers=headers)


class LoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth-login"

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        error_response = _validate_turnstile_or_response(request, serializer.validated_data.get("turnstile_token"))
        if error_response is not None:
            return error_response
        user = serializer.validated_data["user"]

        if not user.two_factor_enabled:
            payload = _build_auth_payload(user)
            return Response(payload, status=status.HTTP_200_OK)

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


class PasswordResetRequestView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email).first()

        response_detail = "If an account exists for that email, you will receive a reset link shortly."

        if not user:
            return Response({"detail": response_detail}, status=status.HTTP_202_ACCEPTED)

        token, raw_token, created = issue_password_reset_token(user)

        if not token:
            return Response({"detail": response_detail}, status=status.HTTP_202_ACCEPTED)

        if raw_token is not None:
            reset_url = (
                f"{settings.FRONTEND_BASE_URL}/reset-password?token={token.token_id}&signature={raw_token}"
            )
            recipient_name = f"{user.first_name} {user.last_name}".strip() or user.email

            try:
                send_password_reset_email(
                    PasswordResetEmail(
                        recipient=user.email,
                        recipient_name=recipient_name,
                        reset_url=reset_url,
                        expires_minutes=getattr(settings, "PASSWORD_RESET_TOKEN_TTL_MINUTES", 24 * 60),
                    )
                )
            except PasswordResetEmailError as exc:
                token.delete()
                return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if not created:
            # Inform the client to wait before retrying, without leaking account existence.
            retry_after = getattr(settings, "PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS", 5 * 60)
            return Response(
                {
                    "detail": response_detail,
                    "retryAfter": retry_after,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        return Response({"detail": response_detail}, status=status.HTTP_202_ACCEPTED)


class PasswordResetValidateView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token: PasswordResetToken = serializer.validated_data["token_obj"]

        return Response(
            {
                "detail": "Reset link is valid.",
                "token": str(token.token_id),
                "expiresAt": token.expires_at.astimezone(dt_timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetCompleteView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token: PasswordResetToken = serializer.validated_data["token_obj"]
        user = serializer.validated_data["user"]
        password = serializer.validated_data["password"]

        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=["password"])

        token.mark_used()
        invalidate_password_reset_tokens(user, exclude_id=token.pk)

        _blacklist_user_tokens(user)
        auth_payload = _build_auth_payload(user)

        return Response(
            {
                "detail": "Password updated successfully.",
                **auth_payload,
            },
            status=status.HTTP_200_OK,
        )


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
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth-2fa"

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
            payload = _build_auth_payload(user)
            return Response(payload, status=status.HTTP_200_OK)

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
        payload = _build_auth_payload(user)
        return Response(payload, status=status.HTTP_200_OK)


class TwoFactorResendView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth-2fa"

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


class TokenRefreshView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth-refresh"

    def post(self, request, *args, **kwargs):
        raw_refresh = request.data.get("refresh")
        if not raw_refresh or not isinstance(raw_refresh, str):
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh_token = RefreshToken(raw_refresh)
        except TokenError:
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED)

        user_id = refresh_token.get("user_id")
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({"detail": "Refresh token is no longer valid."}, status=status.HTTP_401_UNAUTHORIZED)

        payload = _build_auth_payload(user)

        try:
            refresh_token.blacklist()
        except TokenError:
            pass
        except AttributeError:  # pragma: no cover - blacklist app not installed
            pass

        return Response(payload, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth-logout"

    def post(self, request, *args, **kwargs):
        raw_refresh = request.data.get("refresh")
        all_sessions = bool(request.data.get("all"))

        if all_sessions:
            _blacklist_user_tokens(request.user)
            return Response(status=status.HTTP_204_NO_CONTENT)

        if not raw_refresh or not isinstance(raw_refresh, str):
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh_token = RefreshToken(raw_refresh)
        except TokenError:
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST)

        token_user_id = refresh_token.get("user_id")
        if token_user_id != request.user.id:
            return Response({"detail": "Token does not belong to the authenticated user."}, status=status.HTTP_403_FORBIDDEN)

        try:
            refresh_token.blacklist()
        except TokenError:
            pass
        except AttributeError:  # pragma: no cover
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)
