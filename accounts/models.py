import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("Email must be provided")
        if not password:
            raise ValueError("Password must be provided")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Title(models.TextChoices):
        DR = "dr", "Dr"
        MR = "mr", "Mr"
        MRS = "mrs", "Mrs"
        MS = "ms", "Ms"
        PROF = "prof", "Prof"

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    profession = models.CharField(max_length=150, blank=True)
    title = models.CharField(max_length=16, choices=Title.choices, blank=True)
    practice_name = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=128, blank=True)
    two_factor_enabled = models.BooleanField(default=False)
    notify_admin = models.BooleanField(default=True)
    notify_practitioner = models.BooleanField(default=False)
    results_delivery_format = models.CharField(
        max_length=16,
        choices=(
            ("link", "Send as secure link"),
            ("attachment", "Send as PDF attachment"),
        ),
        default="link",
    )
    reply_mode = models.CharField(
        max_length=16,
        choices=(
            ("none", "Do not allow replies"),
            ("practitioner", "Reply to practitioner"),
            ("custom", "Reply to custom address"),
        ),
        default="none",
    )
    results_copy_email = models.EmailField(blank=True)
    reply_email = models.EmailField(blank=True)
    redirect_link = models.URLField(blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = ["first_name", "last_name"]

    def __str__(self) -> str:
        return self.email


class TwoFactorChallenge(models.Model):
    user = models.ForeignKey(
        User,
        related_name="two_factor_challenges",
        on_delete=models.CASCADE,
    )
    challenge_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    code_hash = models.CharField(max_length=128)
    code_salt = models.CharField(max_length=32)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("user", "challenge_id")),
            models.Index(fields=("expires_at",)),
        ]

    def __str__(self) -> str:  # pragma: no cover - repr utility
        return f"TwoFactorChallenge<{self.challenge_id}> for {self.user_id}"


class PasswordResetToken(models.Model):
    user = models.ForeignKey(
        User,
        related_name="password_reset_tokens",
        on_delete=models.CASCADE,
    )
    token_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token_hash = models.CharField(max_length=128, unique=True)
    token_salt = models.CharField(max_length=32)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=("user", "created_at")),
            models.Index(fields=("expires_at",)),
            models.Index(fields=("token_hash",)),
        ]
        ordering = ("-created_at",)

    def mark_used(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at", "updated_at"])

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self) -> str:  # pragma: no cover - repr utility
        return f"PasswordResetToken<{self.pk}> for {self.user_id}"
