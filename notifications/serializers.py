from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "event_type",
            "title",
            "body",
            "payload",
            "created_at",
            "read_at",
            "updated_at",
            "is_read",
        )
        read_only_fields = fields