from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0011_merge_20260902_0138"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatBinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chat_id", models.BigIntegerField(unique=True, verbose_name="Telegram chat_id")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chat_bindings", to="schedule.group", verbose_name="Группа расписания")),
                ("thread_id", models.BigIntegerField(blank=True, null=True, verbose_name="ID топика (message_thread_id)")),
                ("created_by", models.BigIntegerField(blank=True, null=True, verbose_name="Кто привязал (tg user id)")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Привязка чата",
                "verbose_name_plural": "Привязки чатов",
            },
        ),
    ]
