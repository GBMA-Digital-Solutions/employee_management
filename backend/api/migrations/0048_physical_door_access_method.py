from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0047_door_device_mode")]

    operations = [
        migrations.AlterField(
            model_name="roomaccessattempt",
            name="access_method",
            field=models.CharField(
                choices=[
                    ("app", "Employee app"),
                    ("nfc", "NFC (legacy)"),
                    ("bluetooth", "Bluetooth (legacy)"),
                    ("range", "Phone in range (legacy simulator)"),
                    ("door_code", "Door code (legacy simulator)"),
                ],
                max_length=10,
            ),
        ),
    ]
