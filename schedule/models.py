from django.db import models


class Group(models.Model):
    name = models.CharField(max_length=50, unique=True, db_index=True, verbose_name="Группа")

    class Meta:
        ordering = ["name"]
        verbose_name = "Группа"
        verbose_name_plural = "Группы"

    def __str__(self):
        return self.name


class Teacher(models.Model):
    name = models.CharField(max_length=150, unique=True, db_index=True, verbose_name="Преподаватель")

    class Meta:
        ordering = ["name"]
        verbose_name = "Преподаватель"
        verbose_name_plural = "Преподаватели"

    def __str__(self):
        return self.name


class Subject(models.Model):
    name = models.CharField(max_length=250, unique=True, db_index=True, verbose_name="Дисциплина")

    class Meta:
        ordering = ["name"]
        verbose_name = "Дисциплина"
        verbose_name_plural = "Дисциплины"

    def __str__(self):
        return self.name


class Lesson(models.Model):
    date        = models.DateField(db_index=True, verbose_name="Дата")
    day_of_week = models.CharField(max_length=20, blank=True, default="", verbose_name="День недели")
    pair_number = models.PositiveSmallIntegerField(verbose_name="Пара")
    subgroup    = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Подгруппа")
    group       = models.ForeignKey(Group,   on_delete=models.CASCADE, related_name="lessons", verbose_name="Группа")
    teacher     = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="lessons", verbose_name="Преподаватель")
    subject     = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="lessons", verbose_name="Дисциплина")
    room        = models.CharField(max_length=50, blank=True, default="", verbose_name="Аудитория")

    class Meta:
        ordering = ["date", "pair_number", "subgroup"]
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"
        indexes = [
            models.Index(fields=["date", "group"]),
            models.Index(fields=["date", "teacher"]),
            models.Index(fields=["date", "day_of_week"]),
        ]

    def __str__(self):
        sub = f" п.{self.subgroup}" if self.subgroup else ""
        return f"{self.date} пара {self.pair_number}{sub} {self.group} — {self.subject}"
