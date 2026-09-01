from django import template
from django.utils.text import slugify

register = template.Library()


@register.filter
def teacher_link(teacher):
    """Человекочитаемый URL: /teacher/12-иванова-м-р/"""
    return f"/teacher/{teacher.pk}-{slugify(teacher.name, allow_unicode=True)}/"


PAIR_TIMES = {
    1: ("08:30", "10:00"),
    2: ("10:20", "11:50"),
    3: ("12:10", "13:40"),
    4: ("14:00", "15:30"),
    5: ("15:40", "17:10"),
    6: ("17:15", "18:45"),
    7: ("18:50", "20:20"),
    8: ("20:25", "21:55"),
}


@register.filter
def pair_time(pair_number):
    s, e = PAIR_TIMES.get(pair_number, ("", ""))
    return f"{s}–{e}" if s else ""


@register.filter
def pair_start(pair_number):
    return PAIR_TIMES.get(pair_number, ("", ""))[0]


@register.filter
def pair_end(pair_number):
    return PAIR_TIMES.get(pair_number, ("", ""))[1]


@register.filter
def plural_ru(value, forms):
    """Русская плюрализация: {{ n|plural_ru:"пара,пары,пар" }}."""
    n = abs(int(value)) % 100
    form1, form2, form5 = forms.split(",")
    if 11 <= n <= 14:
        return form5
    d = n % 10
    if d == 1:
        return form1
    if 2 <= d <= 4:
        return form2
    return form5
