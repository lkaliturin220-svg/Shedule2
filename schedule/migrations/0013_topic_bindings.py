from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0012_chatbinding"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="thread_id",
            field=models.BigIntegerField(
                blank=True,
                null=True,
                verbose_name="ID топика подписки (message_thread_id)",
            ),
        ),
        migrations.CreateModel(
            name="ChatTopicBinding",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "chat_id",
                    models.BigIntegerField(
                        db_index=True, verbose_name="Telegram chat_id"
                    ),
                ),
                (
                    "thread_id",
                    models.BigIntegerField(
                        db_index=True, verbose_name="ID топика (message_thread_id)"
                    ),
                ),
                (
                    "created_by",
                    models.BigIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Кто привязал (tg user id)",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="topic_bindings",
                        to="schedule.group",
                        verbose_name="Группа расписания",
                    ),
                ),
            ],
            options={
                "verbose_name": "Привязка топика",
                "verbose_name_plural": "Привязки топиков",
                "unique_together": {("chat_id", "thread_id")},
            },
        ),
    ]
