from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import models as db_models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.gzip import gzip_page

from .models import Conspect, ConspectDate, ConspectSubject, Group, InviteCode, Lesson, StudentProfile, Subject, Teacher
from .parser import parse_xlsx


# ──────────────────────────── helpers ────────────────────────────────────────

def _clear_cache():
    cache.clear()


def _dates_for_qs(qs):
    return list(
        qs.values_list("date", flat=True).distinct().order_by("-date")
    )


def _resolve_date(request, dates):
    """Дата из ?date=; иначе — сегодня (если есть занятия); иначе последняя."""
    selected = request.GET.get("date")
    if selected:
        try:
            return datetime.strptime(selected, "%Y-%m-%d").date()
        except ValueError:
            pass
    today = date.today()
    if today in dates:
        return today
    return dates[0] if dates else today


# ──────────────────────────── public: index ──────────────────────────────────

@gzip_page
@cache_page(120)
def index(request):
    groups   = Group.objects.all()
    teachers = Teacher.objects.all()
    return render(request, "schedule/index.html", {
        "groups":   groups,
        "teachers": teachers,
    })


# ──────────────────────────── public: group ──────────────────────────────────

@gzip_page
@cache_page(120)
def group_schedule(request, name):
    group = get_object_or_404(Group, name=name)
    qs    = Lesson.objects.filter(group=group).select_related("teacher", "subject")
    dates = _dates_for_qs(qs)
    sel   = _resolve_date(request, dates)
    lessons = (
        qs.filter(date=sel)
          .order_by("pair_number", "subgroup")
          .select_related("teacher", "subject")
    )
    return render(request, "schedule/group_schedule.html", {
        "group":         group,
        "dates":         dates,
        "selected_date": sel,
        "lessons":       lessons,
        "today":         date.today(),
    })


# ──────────────────────────── public: teacher ────────────────────────────────

@gzip_page
@cache_page(120)
def teacher_schedule(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    qs      = Lesson.objects.filter(teacher=teacher).select_related("group", "subject")
    dates   = _dates_for_qs(qs)
    sel     = _resolve_date(request, dates)
    lessons = (
        qs.filter(date=sel)
          .order_by("pair_number", "subgroup")
          .select_related("group", "subject")
    )
    return render(request, "schedule/teacher_schedule.html", {
        "teacher":       teacher,
        "dates":         dates,
        "selected_date": sel,
        "lessons":       lessons,
        "today":         date.today(),
    })


# ──────────────────────────── admin panel ───────────────────────────────────

@login_required
def admin_panel(request):
    stats = {
        "groups":   Group.objects.count(),
        "teachers": Teacher.objects.count(),
        "subjects": Subject.objects.count(),
        "lessons":  Lesson.objects.count(),
        "dates":    Lesson.objects.values("date").distinct().count(),
    }
    date_stats = (
        Lesson.objects.values("date", "day_of_week")
        .annotate(
            lessons=db_models.Count("id"),
            groups=db_models.Count("group", distinct=True),
        )
        .order_by("-date")
    )
    return render(request, "schedule/admin_panel.html", {
        "stats":      stats,
        "date_stats": date_stats,
    })


@login_required
def upload_schedule(request):
    if request.method != "POST" or "xlsx_file" not in request.FILES:
        return redirect("schedule:admin_panel")

    try:
        result  = parse_xlsx(request.FILES["xlsx_file"])
        lessons = result["lessons"]
        count   = 0

        for row in lessons:
            if not row["subject"] or not row["group"]:
                continue

            # Пропускаем строки без преподавателя — это технические строки
            teacher_name = row["teacher"] or "Не указан"

            group_obj,   _ = Group.objects.get_or_create(name=row["group"])
            teacher_obj, _ = Teacher.objects.get_or_create(name=teacher_name)
            subject_obj, _ = Subject.objects.get_or_create(name=row["subject"])

            Lesson.objects.update_or_create(
                date=row["date"],
                pair_number=row["pair_number"],
                subgroup=row["subgroup"],
                group=group_obj,
                teacher=teacher_obj,
                defaults={
                    "subject":     subject_obj,
                    "room":        row["room"],
                    "day_of_week": row["day_of_week"],
                },
            )
            count += 1

        _clear_cache()
        messages.success(
            request,
            f"✅ Загружено {count} занятий | {result['day_of_week']}, {result['date']}"
        )

    except Exception as exc:
        messages.error(request, f"❌ Ошибка парсинга: {exc}")

    return redirect("schedule:admin_panel")


@login_required
def delete_date(request):
    if request.method == "POST":
        d = request.POST.get("date")
        if d:
            deleted, _ = Lesson.objects.filter(date=d).delete()
            _clear_cache()
            messages.success(request, f"Удалено {deleted} записей за {d}.")
    return redirect("schedule:admin_panel")


# ──────────────────────────── API для Telegram ──────────────────────────────

def api_groups(request):
    groups = list(Group.objects.values_list("name", flat=True))
    return JsonResponse({"groups": groups})


def api_teachers(request):
    teachers = list(Teacher.objects.values("id", "name"))
    return JsonResponse({"teachers": teachers})


def api_group_schedule(request, name):
    d = request.GET.get("date", str(date.today()))
    lessons = (
        Lesson.objects
        .filter(group__name=name, date=d)
        .select_related("teacher", "subject")
        .order_by("pair_number", "subgroup")
    )
    data = [
        {
            "pair":     l.pair_number,
            "subgroup": l.subgroup,
            "subject":  l.subject.name,
            "teacher":  l.teacher.name,
            "room":     l.room,
        }
        for l in lessons
    ]
    return JsonResponse({"group": name, "date": d, "lessons": data})


def api_teacher_schedule(request, pk):
    d = request.GET.get("date", str(date.today()))
    lessons = (
        Lesson.objects
        .filter(teacher_id=pk, date=d)
        .select_related("group", "subject")
        .order_by("pair_number", "subgroup")
    )
    data = [
        {
            "pair":     l.pair_number,
            "subgroup": l.subgroup,
            "subject":  l.subject.name,
            "group":    l.group.name,
            "room":     l.room,
        }
        for l in lessons
    ]
    teacher_name = (
        Teacher.objects.filter(pk=pk).values_list("name", flat=True).first() or ""
    )
    return JsonResponse({"teacher": teacher_name, "date": d, "lessons": data})


# ─────────────────────────── Конспекты и ДЗ ───────────────────────────

@gzip_page
def conspect_list(request):
    """Список предметов — фильтр по группе."""
    all_groups = Group.objects.all()

    # Гость может выбрать/сбросить группу вручную
    if not request.user.is_authenticated:
        if request.GET.get("group") == "":
            request.session.pop("conspect_group", None)
        elif request.GET.get("group"):
            group_name = request.GET.get("group")
            try:
                Group.objects.get(name=group_name)
                request.session["conspect_group"] = group_name
            except Group.DoesNotExist:
                request.session.pop("conspect_group", None)

    user_group = _get_user_group(request)

    if user_group:
        subjects = ConspectSubject.objects.prefetch_related(
            "dates__conspects"
        ).filter(
            dates__conspects__group=user_group
        ).distinct()
    else:
        # Суперюзер или гость без группы — видит всё
        subjects = ConspectSubject.objects.prefetch_related("dates__conspects").all()

    return render(request, "schedule/conspect_list.html", {
        "subjects":   subjects,
        "user_group": user_group,
        "all_groups": all_groups,
        "is_guest":   not request.user.is_authenticated,
    })


def _get_user_group(request):
    """Возвращает группу текущего пользователя (или None для суперюзера/гостя без группы)."""
    if request.user.is_superuser:
        return None  # суперюзер видит всё
    if request.user.is_authenticated:
        try:
            return request.user.student_profile.group
        except Exception:
            return None
    # Гость — группа из сессии
    group_name = request.session.get("conspect_group")
    if group_name:
        try:
            return Group.objects.get(name=group_name)
        except Group.DoesNotExist:
            pass
    return None


@gzip_page
def conspect_subject(request, pk):
    """Cписок дат внутри предмета."""
    subject    = get_object_or_404(ConspectSubject, pk=pk)
    user_group = _get_user_group(request)
    dates_qs   = subject.dates.prefetch_related("conspects")
    if user_group:
        # Показываем только даты где есть конспекты этой группы
        dates_qs = dates_qs.filter(conspects__group=user_group).distinct()
    return render(request, "schedule/conspect_subject.html", {
        "subject":    subject,
        "dates":      dates_qs,
        "user_group": user_group,
    })


@gzip_page
def conspect_date(request, pk):
    """Cписок конспектов за конкретную дату."""
    cdate      = get_object_or_404(ConspectDate.objects.select_related("subject"), pk=pk)
    user_group = _get_user_group(request)
    conspects  = cdate.conspects.all()
    if user_group:
        conspects = conspects.filter(group=user_group)
    return render(request, "schedule/conspect_date.html", {
        "cdate":      cdate,
        "conspects":  conspects,
        "user_group": user_group,
    })


def conspect_upload(request):
    """Загрузка конспекта — только для авторизованных."""
    if not request.user.is_authenticated:
        messages.error(request, "Для загрузки конспектов нужно войти.")
        return redirect("/auth/login/?next=/conspects/upload/")

    # Группа студента
    user_group = None
    try:
        user_group = request.user.student_profile.group
    except Exception:
        pass

    # Предметы из расписания для группы пользователя
    # Суперюзер видит все предметы
    if request.user.is_superuser:
        schedule_subjects = Subject.objects.order_by("name")
    elif user_group:
        schedule_subjects = Subject.objects.filter(
            lessons__group=user_group
        ).distinct().order_by("name")
    else:
        schedule_subjects = Subject.objects.none()

    def _render_upload(post=None):
        return render(request, "schedule/conspect_upload.html", {
            "schedule_subjects": schedule_subjects,
            "post":              post or {},
            "user_group":        user_group,
        })

    if request.method == "POST":
        import os
        from datetime import datetime as dt

        subject_name = request.POST.get("subject_name", "").strip()
        date_str     = request.POST.get("date", "").strip()
        author_name  = request.POST.get("author_name", "").strip()
        file_type    = request.POST.get("file_type", "conspect")
        description  = request.POST.get("description", "").strip()
        upload_file  = request.FILES.get("file")

        errors = []
        if not subject_name:
            errors.append("Укажите предмет.")
        elif not request.user.is_superuser and not schedule_subjects.filter(name=subject_name).exists():
            errors.append("Выберите предмет из списка своей группы.")
        if not date_str:
            errors.append("Укажите дату занятия.")
        if not author_name:
            errors.append("Укажите имя.")
        if not upload_file:
            errors.append("Выберите файл.")

        ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif",
                        ".webp", ".docx", ".doc", ".txt", ".zip"}
        if upload_file:
            ext = os.path.splitext(upload_file.name)[1].lower()
            if ext not in ALLOWED_EXTS:
                errors.append(f"Файл {ext} не разрешён. Разрешены: PDF, изображения, DOCX, TXT, ZIP.")
            if upload_file.size > 20 * 1024 * 1024:
                errors.append("Файл слишком большой (макс. 20 МБ).")

        if errors:
            for e in errors:
                messages.error(request, e)
            return _render_upload(request.POST)

        try:
            lesson_date = dt.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Неверный формат даты.")
            return _render_upload(request.POST)

        subject_obj, _ = ConspectSubject.objects.get_or_create(name=subject_name)
        cdate_obj, _   = ConspectDate.objects.get_or_create(
            subject=subject_obj, date=lesson_date
        )

        Conspect.objects.create(
            conspect_date=cdate_obj,
            author_name=author_name,
            author=request.user,
            group=user_group,
            file=upload_file,
            file_type=file_type,
            description=description,
        )

        messages.success(request, f"✅ Конспект загружен! {subject_name}, {lesson_date.strftime('%d.%m.%Y')}")
        return redirect("schedule:conspect_subject", pk=subject_obj.pk)

    return _render_upload()


def terms(request):
    return render(request, "schedule/terms.html")


# ─────────────────────────── Авторизация студентов ───────────────────────────

def student_register(request):
    """Регистрация студента по инвайт-коду."""
    from django.contrib.auth.models import User
    from django.contrib.auth import login as auth_login

    if request.user.is_authenticated:
        return redirect("schedule:conspect_list")

    if request.method == "POST":
        username   = request.POST.get("username", "").strip()
        password   = request.POST.get("password", "").strip()
        password2  = request.POST.get("password2", "").strip()
        invite_raw = request.POST.get("invite_code", "").strip()

        errors = []
        if not username:
            errors.append("Введите имя пользователя.")
        elif User.objects.filter(username=username).exists():
            errors.append("Это имя уже занято, выберите другое.")
        if not password:
            errors.append("Введите пароль.")
        elif len(password) < 4:
            errors.append("Пароль должен быть не менее 4 символов.")
        if password != password2:
            errors.append("Пароли не совпадают.")
        if not invite_raw:
            errors.append("Введите инвайт-код.")

        invite = None
        if not errors:
            try:
                invite = InviteCode.objects.select_related("group").get(code=invite_raw)
            except InviteCode.DoesNotExist:
                errors.append("Инвайт-код не найден.")
            else:
                if not invite.is_available:
                    errors.append("Инвайт-код исчерпан или деактивирован.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "schedule/student_register.html", {"post": request.POST})

        user = User.objects.create_user(username=username, password=password)
        StudentProfile.objects.create(user=user, group=invite.group, invite=invite)
        invite.used += 1
        invite.save(update_fields=["used"])

        auth_login(request, user)
        messages.success(request, f"Добро пожаловать, {username}! Вы зарегистрированы как студент группы {invite.group}.")
        return redirect("schedule:conspect_list")

    return render(request, "schedule/student_register.html", {"post": {}})


def student_login(request):
    """Вход студента."""
    from django.contrib.auth import authenticate, login as auth_login

    if request.user.is_authenticated:
        return redirect("schedule:conspect_list")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "").strip()
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            next_url = request.POST.get("next") or request.GET.get("next") or "schedule:conspect_list"
            return redirect(next_url)
        else:
            messages.error(request, "Неверное имя пользователя или пароль.")

    return render(request, "schedule/student_login.html", {
        "post": request.POST,
        "next": request.GET.get("next", ""),
    })


def student_logout(request):
    """Выход студента."""
    from django.contrib.auth import logout as auth_logout
    auth_logout(request)
    return redirect("schedule:conspect_list")


def conspect_delete(request, pk):
    """Удаление конспекта — автором или суперюзером."""
    import os
    if not request.user.is_authenticated:
        return redirect("schedule:student_login")

    conspect = get_object_or_404(Conspect, pk=pk)

    if conspect.author != request.user and not request.user.is_superuser:
        messages.error(request, "Вы можете удалять только свои конспекты.")
        return redirect("schedule:conspect_date", pk=conspect.conspect_date.pk)

    if request.method == "POST":
        date_pk = conspect.conspect_date.pk
        try:
            if conspect.file and os.path.isfile(conspect.file.path):
                os.remove(conspect.file.path)
        except Exception:
            pass
        conspect.delete()
        messages.success(request, "Конспект удалён.")
        # Если модератор — возвращаем на страницу модерации
        if request.user.is_superuser:
            return redirect("schedule:conspect_moderation")
        return redirect("schedule:conspect_date", pk=date_pk)

    return render(request, "schedule/conspect_confirm_delete.html", {"conspect": conspect})


def conspect_moderation(request):
    """Страница модерации конспектов — только для суперюзеров."""
    if not request.user.is_superuser:
        messages.error(request, "Доступ запрещён.")
        return redirect("schedule:conspect_list")

    # Фильтры
    group_filter = request.GET.get("group", "")
    user_filter  = request.GET.get("user", "").strip()

    conspects = Conspect.objects.select_related(
        "conspect_date__subject", "author", "group"
    ).order_by("-uploaded_at")

    if group_filter:
        conspects = conspects.filter(group__name=group_filter)
    if user_filter:
        conspects = conspects.filter(
            db_models.Q(author_name__icontains=user_filter) |
            db_models.Q(author__username__icontains=user_filter)
        )

    all_groups = Group.objects.all()

    return render(request, "schedule/conspect_moderation.html", {
        "conspects":    conspects,
        "all_groups":   all_groups,
        "group_filter": group_filter,
        "user_filter":  user_filter,
    })


def feedback(request):
    import os, requests as req
    from .models import Feedback

    if request.method == "POST":
        category = request.POST.get("category", "other")
        text     = request.POST.get("text", "").strip()
        contact  = request.POST.get("contact", "").strip()

        if text:
            fb = Feedback.objects.create(category=category, text=text, contact=contact)

            # Отправить в Telegram @TIRED_Kiwi
            token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            admin_id = os.getenv("ADMIN_CHAT_ID", "")
            if token and admin_id:
                cat_labels = {"bug": "🐛 Баг", "idea": "💡 Идея", "other": "📨 Другое"}
                label = cat_labels.get(category, category)
                msg = (
                    f"<b>Новое сообщение #{fb.pk}</b>\n"
                    f"{label}\n\n"
                    f"{text}\n\n"
                    f"Контакт: {contact or 'не указан'}"
                )
                try:
                    req.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": admin_id, "text": msg, "parse_mode": "HTML"},
                        timeout=5,
                    )
                except Exception:
                    pass

            messages.success(request, "Спасибо! Сообщение отправлено.")
            return redirect("schedule:feedback")
        else:
            messages.error(request, "Сообщение не может быть пустым.")

    return render(request, "schedule/feedback.html")

