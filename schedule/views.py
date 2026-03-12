from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import models as db_models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import cache_page
from django.views.decorators.gzip import gzip_page

from .models import Group, Lesson, Subject, Teacher
from .parser import parse_xlsx


# ──────────────────────────── helpers ────────────────────────────────────────

def _clear_cache():
    cache.clear()


def _dates_for_qs(qs):
    return list(
        qs.values_list("date", flat=True).distinct().order_by("-date")
    )


def _resolve_date(request, dates):
    selected = request.GET.get("date")
    if selected:
        try:
            return datetime.strptime(selected, "%Y-%m-%d").date()
        except ValueError:
            pass
    return dates[0] if dates else date.today()


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
