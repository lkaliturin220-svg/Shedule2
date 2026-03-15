from django.contrib import admin
from .models import Group, Teacher, Subject, Lesson, InviteCode, StudentProfile, Conspect, Feedback, ConspectSubject


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


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display  = ["code", "group", "used", "limit", "is_active", "created_at"]
    list_filter   = ["group", "is_active"]
    search_fields = ["code"]
    list_editable = ["is_active", "limit"]


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display  = ["user", "group", "invite"]
    list_filter   = ["group"]
    search_fields = ["user__username"]
    raw_id_fields = ["user", "group", "invite"]


@admin.register(Conspect)
class ConspectAdmin(admin.ModelAdmin):
    list_display  = ["author_name", "author", "conspect_date", "file_type", "uploaded_at"]
    list_filter   = ["file_type"]
    search_fields = ["author_name", "description"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display  = ["category", "text", "contact", "created_at", "is_read"]
    list_filter   = ["category", "is_read"]
    list_editable = ["is_read"]


@admin.register(ConspectSubject)
class ConspectSubjectAdmin(admin.ModelAdmin):
    list_display  = ["name", "created_at"]
    search_fields = ["name"]
