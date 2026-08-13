"""Общие сервисные функции для работы с расписанием."""
from .models import Group, Lesson, Subject, Teacher

FALLBACK_TEACHER = "Не указан"


def save_lessons(lessons, *, update_existing=True) -> tuple[int, int]:
    """
    Сохраняет занятия из результата parse_xlsx.

    update_existing=True  — update_or_create (обновляет существующие),
                            как при ручной загрузке через админку.
    update_existing=False — get_or_create (не трогает существующее),
                            как при синхронизации с Яндекс.Диска.

    Возвращает (обработано, создано_новых).
    """
    processed = 0
    created = 0
    for row in lessons:
        subject_name = row.get("subject")
        group_name = row.get("group")
        if not subject_name or not group_name:
            continue

        teacher_name = row.get("teacher") or FALLBACK_TEACHER

        group_obj, _   = Group.objects.get_or_create(name=group_name)
        teacher_obj, _ = Teacher.objects.get_or_create(name=teacher_name)
        subject_obj, _ = Subject.objects.get_or_create(name=subject_name)

        defaults = {
            "subject":     subject_obj,
            "room":        row.get("room", ""),
            "day_of_week": row.get("day_of_week", ""),
        }
        lookup = {
            "date":        row["date"],
            "pair_number": row["pair_number"],
            "subgroup":    row.get("subgroup"),
            "group":       group_obj,
        }

        if update_existing:
            _, was_created = Lesson.objects.update_or_create(
                **lookup, teacher=teacher_obj, defaults=defaults
            )
        else:
            _, was_created = Lesson.objects.get_or_create(
                **lookup, teacher=teacher_obj, defaults={**defaults, "teacher": teacher_obj}
            )

        processed += 1
        created += 1 if was_created else 0

    return processed, created
