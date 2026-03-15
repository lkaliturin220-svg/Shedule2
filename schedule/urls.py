from django.urls import path
from . import views

app_name = "schedule"

urlpatterns = [
    # Публичные страницы
    path("",                              views.index,            name="index"),
    path("group/<str:name>/",             views.group_schedule,   name="group"),
    path("teacher/<int:pk>/",             views.teacher_schedule, name="teacher"),

    # Панель администратора
    path("admin-panel/",                  views.admin_panel,      name="admin_panel"),
    path("upload/",                       views.upload_schedule,  name="upload"),
    path("delete-date/",                  views.delete_date,      name="delete_date"),

    # Конспекты и ДЗ
    path("conspects/",                          views.conspect_list,    name="conspect_list"),
    path("conspects/upload/",                   views.conspect_upload,  name="conspect_upload"),
    path("conspects/subject/<int:pk>/",         views.conspect_subject, name="conspect_subject"),
    path("conspects/date/<int:pk>/",            views.conspect_date,    name="conspect_date"),

    # Конспекты — удаление
    path("conspects/delete/<int:pk>/",           views.conspect_delete,  name="conspect_delete"),

    # Авторизация студентов
    path("auth/register/",               views.student_register, name="student_register"),
    path("auth/login/",                  views.student_login,    name="student_login"),
    path("auth/logout/",                 views.student_logout,   name="student_logout"),

    # Пользовательское соглашение
    path("terms/",                       views.terms,            name="terms"),
    path("feedback/",                    views.feedback,         name="feedback"),

    # API для Telegram-бота
    path("api/groups/",                         views.api_groups,            name="api_groups"),
    path("api/teachers/",                        views.api_teachers,           name="api_teachers"),
    path("api/schedule/group/<str:name>/",       views.api_group_schedule,    name="api_group_schedule"),
    path("api/schedule/teacher/<int:pk>/",       views.api_teacher_schedule,  name="api_teacher_schedule"),
]
