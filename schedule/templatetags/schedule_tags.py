from django import template

register = template.Library()


@register.filter
def pair_time(pair_number):
    times = {
        1: "08:30–10:00",
        2: "10:20–11:50",
        3: "12:10–13:40",
        4: "14:00–15:30",
        5: "15:40–17:10",
        6: "17:15–18:45",
        7: "18:50–20:20",
        8: "20:25–21:55",
    }
    return times.get(pair_number, "")


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
