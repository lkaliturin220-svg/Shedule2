from django.contrib import admin
from .models import Group, Teacher, Subject, Lesson


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display  = ["name"]
    search_fields = ["name"]


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display  = ["name"]
    search_fields = ["name"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display  = ["name"]
    search_fields = ["name"]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display   = ["date", "day_of_week", "pair_number", "subgroup", "group", "teacher", "subject", "room"]
    list_filter    = ["date", "group", "teacher"]
    search_fields  = ["group__name", "teacher__name", "subject__name"]
    raw_id_fields  = ["group", "teacher", "subject"]
    date_hierarchy = "date"
