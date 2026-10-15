from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("api", "0040_workday_sessions_and_settings")]
    operations = [
        migrations.CreateModel(name="MonitoringConsent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("notice_version", models.CharField(default="1", max_length=20)),
            ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
            ("employee", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                               related_name="monitoring_consent", to="api.employee")),
        ]),
        migrations.CreateModel(name="MonitoringAgent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("token_hash", models.CharField(max_length=64, unique=True)),
            ("is_active", models.BooleanField(default=True)),
            ("issued_at", models.DateTimeField(auto_now_add=True)),
            ("last_seen_at", models.DateTimeField(blank=True, null=True)),
            ("employee", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                               related_name="monitoring_agent", to="api.employee")),
        ]),
        migrations.CreateModel(name="ActivityClassification", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("domain", models.CharField(max_length=253)),
            ("category", models.CharField(choices=[("work", "Work-related"), ("social", "Social media"),
                                                   ("entertainment", "Entertainment"), ("other", "Other")],
                                          default="other", max_length=20)),
            ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name="activity_classifications", to="api.business")),
        ], options={"ordering": ["domain"], "constraints": [models.UniqueConstraint(
            fields=("business", "domain"), name="unique_business_activity_domain")]}),
        migrations.CreateModel(name="ActivityEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("source", models.CharField(choices=[("windows", "Windows desktop agent"),
                                                 ("browser", "Browser extension")], max_length=10)),
            ("kind", models.CharField(choices=[("application", "Desktop application"),
                                               ("website", "Website")], max_length=12)),
            ("resource", models.CharField(max_length=500)),
            ("domain", models.CharField(blank=True, db_index=True, max_length=253)),
            ("started_at", models.DateTimeField(db_index=True)),
            ("ended_at", models.DateTimeField()),
            ("duration_seconds", models.PositiveIntegerField()),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name="activity_events", to="api.employee")),
        ], options={"ordering": ["-started_at", "-id"], "indexes": [models.Index(
            fields=["employee", "started_at"], name="api_activit_employe_9d051a_idx")]}),
    ]
