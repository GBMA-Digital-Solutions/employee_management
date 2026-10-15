from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0039_attendance_visits")]

    operations = [
        migrations.AddField(
            model_name="business", name="expected_daily_hours",
            field=models.DecimalField(decimal_places=2, default=Decimal("8.00"), max_digits=4,
                                      validators=[MinValueValidator(Decimal("0.25")),
                                                  MaxValueValidator(Decimal("24.00"))]),
        ),
        migrations.AddField(model_name="business", name="workday_start",
                            field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name="business", name="workday_end",
                            field=models.TimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="business", name="reminder_minutes",
            field=models.PositiveIntegerField(default=15, validators=[MaxValueValidator(240)]),
        ),
        migrations.AddField(model_name="accountprofile", name="token_version",
                            field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="attendance", name="finalized_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="attendance", name="departure_reminder_sent_at",
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.RunSQL(
            "UPDATE api_attendance SET finalized_at = check_out_at WHERE check_out_at IS NOT NULL",
            migrations.RunSQL.noop,
        ),
    ]
