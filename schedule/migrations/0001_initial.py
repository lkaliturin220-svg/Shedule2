# Generated migration — created manually
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Group",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("name", models.CharField(db_index=True, max_length=50, unique=True, verbose_name="Группа")),
            ],
            options={"ordering": ["name"], "verbose_name": "Группа", "verbose_name_plural": "Группы"},
        ),
        migrations.CreateModel(
            name="Teacher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("name", models.CharField(db_index=True, max_length=150, unique=True, verbose_name="Преподаватель")),
            ],
            options={"ordering": ["name"], "verbose_name": "Преподаватель", "verbose_name_plural": "Преподаватели"},
        ),
        migrations.CreateModel(
            name="Subject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("name", models.CharField(db_index=True, max_length=250, unique=True, verbose_name="Дисциплина")),
            ],
            options={"ordering": ["name"], "verbose_name": "Дисциплина", "verbose_name_plural": "Дисциплины"},
        ),
        migrations.CreateModel(
            name="Lesson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True)),
                ("date", models.DateField(db_index=True, verbose_name="Дата")),
                ("day_of_week", models.CharField(blank=True, default="", max_length=20, verbose_name="День недели")),
                ("pair_number", models.PositiveSmallIntegerField(verbose_name="Пара")),
                ("subgroup", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Подгруппа")),
                ("room", models.CharField(blank=True, default="", max_length=50, verbose_name="Аудитория")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lessons", to="schedule.group", verbose_name="Группа")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lessons", to="schedule.teacher", verbose_name="Преподаватель")),
                ("subject", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lessons", to="schedule.subject", verbose_name="Дисциплина")),
            ],
            options={"ordering": ["date", "pair_number", "subgroup"], "verbose_name": "Занятие", "verbose_name_plural": "Занятия"},
        ),
        migrations.AddIndex(
            model_name="lesson",
            index=models.Index(fields=["date", "group"], name="lesson_date_group_idx"),
        ),
        migrations.AddIndex(
            model_name="lesson",
            index=models.Index(fields=["date", "teacher"], name="lesson_date_teacher_idx"),
        ),
        migrations.AddIndex(
            model_name="lesson",
            index=models.Index(fields=["date", "day_of_week"], name="lesson_date_dow_idx"),
        ),
    ]
