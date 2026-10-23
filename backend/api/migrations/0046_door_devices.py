import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("api", "0045_alter_business_expected_daily_hours"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="DoorDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("device_id", models.CharField(max_length=100, unique=True)),
                ("secret_hash", models.CharField(max_length=64)),
                ("enabled", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("relay_locked", models.BooleanField(default=True)),
                ("last_command_id", models.UUIDField(blank=True, null=True)),
                ("last_acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("room", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="door_device", to="api.room")),
            ],
        ),
        migrations.CreateModel(
            name="DoorUnlockCommand",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("state", models.CharField(choices=[("created", "Created"), ("pending", "Pending"), ("claimed", "Claimed"), ("executing", "Executing"), ("completed", "Completed"), ("expired", "Expired"), ("failed", "Failed")], default="pending", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("failure_code", models.CharField(blank=True, max_length=80)),
                ("access_attempt", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="device_command", to="api.roomaccessattempt")),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commands", to="api.doordevice")),
                ("requested_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddIndex(model_name="doorunlockcommand", index=models.Index(fields=["device", "state", "expires_at"], name="api_doorunl_device__2d3e68_idx")),
    ]
