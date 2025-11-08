from typing import List

from django.utils.text import slugify
from rest_framework import serializers

from .models import Client, ClientGroup, ClientGroupMembership


def generate_unique_client_slug(owner_id: int, base: str) -> str:
    base_slug = slugify(base) or "client"
    slug = base_slug
    suffix = 1

    while Client.objects.filter(owner_id=owner_id, slug=slug).exists():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    return slug


def generate_unique_group_slug(owner_id: int, base: str) -> str:
    base_slug = slugify(base) or "group"
    slug = base_slug
    suffix = 1

    while ClientGroup.objects.filter(owner_id=owner_id, slug=slug).exists():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    return slug


def update_client_group_cache(client: Client) -> None:
    names = list(client.group_memberships.select_related("group").values_list("group__name", flat=True))
    client.groups = ", ".join(name for name in names if name)
    client.save(update_fields=["groups"])


class ClientGroupSerializer(serializers.ModelSerializer):
    member_slugs = serializers.ListField(child=serializers.SlugField(), write_only=True, required=False)
    members = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ClientGroup
        fields = (
            "id",
            "slug",
            "name",
            "member_slugs",
            "members",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "created_at", "updated_at", "owner")

    def get_members(self, obj: ClientGroup):
        memberships = obj.memberships.select_related("client")
        serialized = []
        for membership in memberships:
            client = membership.client
            serialized.append(
                {
                    "slug": client.slug,
                    "name": f"{client.first_name} {client.last_name}".strip() or client.email or "Unnamed client",
                    "email": client.email,
                }
            )
        return serialized

    def validate_member_slugs(self, slugs):
        owner = self.context["request"].user
        missing = set(slugs) - set(
            Client.objects.filter(owner=owner, slug__in=slugs).values_list("slug", flat=True)
        )
        if missing:
            raise serializers.ValidationError(f"Unknown client slugs: {', '.join(missing)}")
        return slugs

    def create(self, validated_data):
        request = self.context.get("request")
        owner = getattr(request, "user", None)
        if owner is None or not owner.is_authenticated:
            raise serializers.ValidationError("Authenticated user required to create client groups.")

        member_slugs = validated_data.pop("member_slugs", [])
        slug = validated_data.get("slug")
        if not slug:
            validated_data["slug"] = generate_unique_group_slug(owner.pk, validated_data.get("name", "group"))
        else:
            validated_data["slug"] = slugify(slug)

        validated_data["owner"] = owner
        group = super().create(validated_data)
        if member_slugs:
            self._sync_memberships(group, member_slugs)
        return group

    def update(self, instance, validated_data):
        member_slugs = validated_data.pop("member_slugs", None)
        slug = validated_data.get("slug")
        if slug:
            validated_data["slug"] = slugify(slug)

        group = super().update(instance, validated_data)
        if member_slugs is not None:
            self._sync_memberships(group, member_slugs)
        return group

    def _sync_memberships(self, group: ClientGroup, slugs: List[str]):
        owner_clients = {
            client.slug: client
            for client in Client.objects.filter(owner=group.owner, slug__in=slugs)
        }

        existing = {membership.client.slug: membership for membership in group.memberships.select_related("client")}
        affected_clients: dict[int, Client] = {}

        # Remove memberships not in the new list
        for slug, membership in list(existing.items()):
            if slug not in owner_clients:
                affected_clients[membership.client_id] = membership.client
                membership.delete()
                existing.pop(slug)

        # Add new memberships
        for slug, client in owner_clients.items():
            if slug not in existing:
                ClientGroupMembership.objects.create(group=group, client=client)
                affected_clients[client.pk] = client

        # Refresh cached summaries
        for client in affected_clients.values():
            update_client_group_cache(client)
class ClientSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    group_slugs = serializers.ListField(child=serializers.SlugField(), write_only=True, required=False)

    groups = serializers.SerializerMethodField()

    class Meta:
        model = Client
        read_only_fields = ("id", "slug", "created_at", "updated_at", "owner")
        fields = (
            "id",
            "slug",
            "first_name",
            "last_name",
            "name",
            "email",
            "dob",
            "gender",
            "groups",
            "is_active",
            "last_assessed",
            "informant1_name",
            "informant1_email",
            "informant2_name",
            "informant2_email",
            "groups",
            "group_slugs",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "slug": {"required": False, "allow_null": True, "allow_blank": True},
        }

        read_only_fields = ("id", "created_at", "updated_at", "owner", "groups")

    def get_name(self, obj: Client) -> str:
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.email or "Unnamed client"

    def get_groups(self, obj: Client) -> str:
        names = obj.group_memberships.select_related("group").values_list("group__name", flat=True)
        return ", ".join(name for name in names if name)

    def validate_group_slugs(self, slugs: List[str]) -> List[str]:
        request = self.context.get("request")
        owner = getattr(request, "user", None)
        if owner is None or not owner.is_authenticated:
            raise serializers.ValidationError("Authenticated user required to update group memberships.")

        missing = set(slugs) - set(
            ClientGroup.objects.filter(owner=owner, slug__in=slugs).values_list("slug", flat=True)
        )
        if missing:
            raise serializers.ValidationError(f"Unknown group slugs: {', '.join(sorted(missing))}")
        return slugs

    def create(self, validated_data):
        request = self.context.get("request")
        owner = getattr(request, "user", None)
        if owner is None or not owner.is_authenticated:
            raise serializers.ValidationError("Authenticated user required to create clients.")

        group_slugs = validated_data.pop("group_slugs", [])
        validated_data.pop("groups", None)
        slug = validated_data.get("slug")
        if not slug:
            base = f"{validated_data.get('first_name', '')} {validated_data.get('last_name', '')}".strip() or owner.email
            validated_data["slug"] = generate_unique_client_slug(owner.pk, base)
        else:
            validated_data["slug"] = slugify(slug)

        validated_data["owner"] = owner
        client = super().create(validated_data)
        if group_slugs:
            self._sync_group_memberships(client, group_slugs)
        else:
            update_client_group_cache(client)
        return client


class ClientImportRowSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField()
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=[choice[0] for choice in Client.Gender.choices],
        required=False,
        allow_blank=True,
    )
    informant1_name = serializers.CharField(required=False, allow_blank=True)
    informant1_email = serializers.EmailField(required=False, allow_blank=True)
    informant2_name = serializers.CharField(required=False, allow_blank=True)
    informant2_email = serializers.EmailField(required=False, allow_blank=True)
    slug = serializers.SlugField(required=False)

    def validate(self, attrs):
        if not attrs.get("first_name") and not attrs.get("last_name"):
            raise serializers.ValidationError("Provide at least a first or last name.")
        return attrs
