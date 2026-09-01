from django.contrib.auth.models import User
from django.db import models
from django.utils.text import slugify  # добавить импорт сверху


class Group(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=150, unique=True, blank=True, null=True, allow_unicode=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            # Заменяем проблемные символы перед созданием слага
            safe_name = self.name.replace('/', '-').replace(' ', '-')
            self.slug = slugify(safe_name, allow_unicode=True)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('group_detail', kwargs={'slug': self.slug})

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


class Feedback(models.Model):
    CATEGORY_CHOICES = [
        ("bug",  "Баг / ошибка"),
        ("idea", "Идея / предложение"),
        ("other", "Другое"),
    ]
    category   = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default="other", verbose_name="Категория")
    text       = models.TextField(verbose_name="Сообщение")
    contact    = models.CharField(max_length=100, blank=True, default="", verbose_name="Контакт (необязательно)")
    created_at = models.DateTimeField(auto_now_add=True)
    is_read    = models.BooleanField(default=False, verbose_name="Прочитано")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Обратная связь"
        verbose_name_plural = "Обратная связь"

    def __str__(self):
        return f"[{self.get_category_display()}] {self.text[:50]}"


# ── Конспекты и ДЗ ──────────────────────────────────────────────────────────

class ConspectSubject(models.Model):
    """Предмет в разделе конспектов (может отличаться от Subject в расписании)."""
    name       = models.CharField(max_length=200, unique=True, verbose_name="Предмет")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Предмет (конспекты)"
        verbose_name_plural = "Предметы (конспекты)"

    def __str__(self):
        return self.name


class ConspectDate(models.Model):
    """Дата занятия внутри предмета."""
    subject    = models.ForeignKey(ConspectSubject, on_delete=models.CASCADE,
                                   related_name="dates", verbose_name="Предмет")
    date       = models.DateField(verbose_name="Дата занятия")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        unique_together = [("subject", "date")]
        verbose_name = "Дата (конспекты)"
        verbose_name_plural = "Даты (конспекты)"

    def __str__(self):
        return f"{self.subject.name} — {self.date.strftime('%d.%m.%Y')}"


def conspect_upload_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f"conspects/{instance.conspect_date.subject_id}/{instance.conspect_date.date}/{instance.author_name}{ext}"


class Conspect(models.Model):
    """Конспект или ДЗ от конкретного автора."""
    TYPE_CHOICES = [
        ("conspect", "Конспект"),
        ("hw",       "Домашнее задание"),
        ("other",    "Другое"),
    ]
    conspect_date = models.ForeignKey(ConspectDate, on_delete=models.CASCADE,
                                      related_name="conspects", verbose_name="Дата")
    author_name   = models.CharField(max_length=100, verbose_name="Имя автора")
    author        = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="conspects", verbose_name="Аккаунт автора")
    group         = models.ForeignKey("Group", on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="conspects", verbose_name="Группа")
    file          = models.FileField(upload_to=conspect_upload_path, verbose_name="Файл")
    file_type     = models.CharField(max_length=10, choices=TYPE_CHOICES,
                                     default="conspect", verbose_name="Тип")
    description   = models.CharField(max_length=200, blank=True, default="",
                                     verbose_name="Описание (необязательно)")
    uploaded_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["author_name"]
        verbose_name = "Конспект"
        verbose_name_plural = "Конспекты"

    def __str__(self):
        return f"{self.author_name} — {self.conspect_date}"

    @property
    def filename(self):
        import os
        return os.path.basename(self.file.name)

    @property
    def file_ext(self):
        import os
        return os.path.splitext(self.file.name)[1].lower().lstrip(".")


class InviteCode(models.Model):
    """Инвайт-код для регистрации студентов."""
    code       = models.CharField(max_length=50, unique=True, verbose_name="Код")
    group      = models.ForeignKey(Group, on_delete=models.CASCADE,
                                   related_name="invite_codes", verbose_name="Группа")
    limit      = models.PositiveSmallIntegerField(default=30, verbose_name="Лимит студентов")
    used       = models.PositiveSmallIntegerField(default=0, verbose_name="Использовано")
    is_active  = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["group", "code"]
        verbose_name = "Инвайт-код"
        verbose_name_plural = "Инвайт-коды"

    def __str__(self):
        return f"{self.code} ({self.group}) {self.used}/{self.limit}"

    @property
    def is_available(self):
        return self.is_active and self.used < self.limit


class StudentProfile(models.Model):
    """Профиль студента — привязка к группе."""
    user       = models.OneToOneField(User, on_delete=models.CASCADE,
                                      related_name="student_profile", verbose_name="Пользователь")
    group      = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True,
                                   related_name="students", verbose_name="Группа")
    invite     = models.ForeignKey(InviteCode, on_delete=models.SET_NULL, null=True, blank=True,
                                   verbose_name="Инвайт-код")

    class Meta:
        verbose_name = "Профиль студента"
        verbose_name_plural = "Профили студентов"

    def __str__(self):
        return f"{self.user.username} / {self.group}"


class Subscription(models.Model):
    """Подписка студента на уведомления о расписании своей группы."""
    chat_id    = models.BigIntegerField(db_index=True, verbose_name="Telegram chat_id")
    group      = models.ForeignKey(Group, on_delete=models.CASCADE,
                                   related_name="subscriptions", verbose_name="Группа")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("chat_id", "group")]
        verbose_name        = "Подписка"
        verbose_name_plural = "Подписки"

    def __str__(self):
        return f"chat={self.chat_id} → {self.group}"


class ViewCounter(models.Model):
    """Счётчик просмотров страниц (без IP и куки — только агрегат)."""
    key   = models.CharField(max_length=120, unique=True, db_index=True)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Счётчик просмотров"
        verbose_name_plural = "Счётчики просмотров"

    def __str__(self):
        return f"{self.key}: {self.count}"
