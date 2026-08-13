from django import template

from schedule.const import PAIR_TIMES

register = template.Library()


@register.filter
def pair_time(pair_number):
    return PAIR_TIMES.get(pair_number, "")
