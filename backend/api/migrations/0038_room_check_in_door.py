from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0037_door_range_check")]

    operations = [
        migrations.AddField(
            model_name="room",
            name="is_check_in_door",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="room",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_check_in_door=True),
                fields=("business",),
                name="unique_business_check_in_door",
            ),
        ),
    ]
