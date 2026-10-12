from django.db import migrations, models
import django.db.models.deletion


def copy_existing_attendance(apps, schema_editor):
    Attendance = apps.get_model("api", "Attendance")
    AttendanceVisit = apps.get_model("api", "AttendanceVisit")
    AttendanceVisit.objects.bulk_create([
        AttendanceVisit(
            attendance_id=row.pk,
            check_in_at=row.check_in_at,
            check_out_at=row.check_out_at,
        )
        for row in Attendance.objects.exclude(check_in_at=None)
    ])


class Migration(migrations.Migration):
    dependencies = [("api", "0038_room_check_in_door")]

    operations = [
        migrations.CreateModel(
            name="AttendanceVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("check_in_at", models.DateTimeField()),
                ("check_out_at", models.DateTimeField(blank=True, null=True)),
                ("attendance", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name="visits", to="api.attendance")),
            ],
            options={"ordering": ["check_in_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="attendancevisit",
            constraint=models.UniqueConstraint(
                condition=models.Q(check_out_at__isnull=True), fields=("attendance",),
                name="unique_open_visit_per_attendance",
            ),
        ),
        migrations.RunPython(copy_existing_attendance, migrations.RunPython.noop),
    ]
