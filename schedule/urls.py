from django.urls import path, re_path
from . import views

app_name = "schedule"

urlpatterns = [
    path("",                              views.index,            name="index"),
    re_path(r"^group/(?P<name>.+)/$",     views.group_schedule,   name="group"),
    path("teacher/<int:pk>/",             views.teacher_schedule, name="teacher"),

    path("admin-panel/",                  views.admin_panel,      name="admin_panel"),
    path("upload/",                       views.upload_schedule,  name="upload"),
    path("delete-date/",                  views.delete_date,      name="delete_date"),

    path("conspects/",                          views.conspect_list,    name="conspect_list"),
    path("conspects/upload/",                   views.conspect_upload,  name="conspect_upload"),
    path("conspects/subject/<int:pk>/",         views.conspect_subject, name="conspect_subject"),
    path("conspects/date/<int:pk>/",            views.conspect_date,    name="conspect_date"),
    path("conspects/delete/<int:pk>/",          views.conspect_delete,  name="conspect_delete"),

    path("auth/register/",               views.student_register, name="student_register"),
    path("auth/login/",                  views.student_login,    name="student_login"),
    path("auth/logout/",                 views.student_logout,   name="student_logout"),

    path("terms/",                       views.terms,            name="terms"),
    path("feedback/",                    views.feedback,         name="feedback"),

    path("api/groups/",                         views.api_groups,            name="api_groups"),
    path("api/teachers/",                       views.api_teachers,          name="api_teachers"),
    re_path(r"^api/schedule/group/(?P<name>.+)/$", views.api_group_schedule,   name="api_group_schedule"),
    path("api/schedule/teacher/<int:pk>/",       views.api_teacher_schedule, name="api_teacher_schedule"),
]
