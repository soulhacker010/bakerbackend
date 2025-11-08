from django.contrib import admin

from .models import Client, ClientGroup, ClientGroupMembership


class ClientGroupMembershipInline(admin.TabularInline):
    model = ClientGroupMembership
    extra = 0
    raw_id_fields = ("client",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "owner", "is_active", "last_assessed", "created_at")
    list_filter = ("is_active", "gender")
    search_fields = ("first_name", "last_name", "email", "slug")
    readonly_fields = ("created_at", "updated_at")

    def full_name(self, obj: Client) -> str:
        return f"{obj.first_name} {obj.last_name}".strip() or obj.email or "Unnamed client"

    full_name.short_description = "Client"


@admin.register(ClientGroup)
class ClientGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")
    inlines = (ClientGroupMembershipInline,)


@admin.register(ClientGroupMembership)
class ClientGroupMembershipAdmin(admin.ModelAdmin):
    list_display = ("group", "client", "added_at")
    search_fields = ("group__name", "client__first_name", "client__last_name", "client__email")
    list_select_related = ("group", "client")
