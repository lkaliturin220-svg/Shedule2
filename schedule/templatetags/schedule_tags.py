from django import template

register = template.Library()


@register.filter
def pair_time(pair_number):
    times = {
        1: "08:00–09:30",
        2: "09:40–11:10",
        3: "11:30–13:00",
        4: "13:20–14:50",
        5: "15:00–16:30",
        6: "16:40–18:10",
        7: "18:20–19:50",
        8: "20:00–21:30",
    }
    return times.get(pair_number, "")
