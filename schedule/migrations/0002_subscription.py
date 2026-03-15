from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chat_id", models.BigIntegerField(db_index=True, verbose_name="Telegram chat_id")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("group", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="subscriptions",
                    to="schedule.group",
                    verbose_name="Group",
                )),
            ],
            options={
                "verbose_name": "Subscription",
                "verbose_name_plural": "Subscriptions",
                "unique_together": {("chat_id", "group")},
            },
        ),
    ]
