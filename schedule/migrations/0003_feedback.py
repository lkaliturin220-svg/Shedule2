from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0002_subscription"),
    ]

    operations = [
        migrations.CreateModel(
            name="Feedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(
                    choices=[("bug", "Bug"), ("idea", "Idea"), ("other", "Other")],
                    default="other", max_length=10, verbose_name="Category"
                )),
                ("text", models.TextField(verbose_name="Message")),
                ("contact", models.CharField(blank=True, default="", max_length=100, verbose_name="Contact")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_read", models.BooleanField(default=False, verbose_name="Read")),
            ],
            options={
                "verbose_name": "Feedback",
                "verbose_name_plural": "Feedback",
                "ordering": ["-created_at"],
            },
        ),
    ]
