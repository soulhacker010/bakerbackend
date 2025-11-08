from django.conf import settings
from django.db import models


class Client(models.Model):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        DIVERSE = "diverse", "Gender diverse or non-binary"

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="clients",
        on_delete=models.CASCADE,
        help_text="Clinician who manages this client record.",
    )

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=16, choices=Gender.choices, blank=True)
    groups = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_assessed = models.DateField(blank=True, null=True)

    informant1_name = models.CharField(max_length=150, blank=True)
    informant1_email = models.EmailField(blank=True)
    informant2_name = models.CharField(max_length=150, blank=True)
    informant2_email = models.EmailField(blank=True)

    slug = models.SlugField(max_length=180)

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("owner", "slug")

    def __str__(self) -> str:
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email or f"Client {self.pk}"


class ClientGroup(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="client_groups",
        on_delete=models.CASCADE,
        help_text="Clinician who manages this client group.",
    )

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=180)

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("owner", "slug")

    def __str__(self) -> str:
        return self.name


class ClientGroupMembership(models.Model):
    added_at = models.DateTimeField(auto_now_add=True)

    group = models.ForeignKey(
        ClientGroup,
        related_name="memberships",
        on_delete=models.CASCADE,
    )
    client = models.ForeignKey(
        Client,
        related_name="group_memberships",
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ("group", "client")

    def __str__(self) -> str:
        return f"{self.client} in {self.group}"

