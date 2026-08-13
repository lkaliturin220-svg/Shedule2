import io
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from schedule.models import (
    Conspect,
    ConspectDate,
    ConspectSubject,
    Group,
    InviteCode,
    Lesson,
    StudentProfile,
    Subject,
    Teacher,
    conspect_upload_path,
)
from schedule.parser import parse_xlsx

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class ScheduleTestCase(TestCase):
    pass


class SchedulePagesTests(ScheduleTestCase):
    def setUp(self):
        self.group = Group.objects.create(name="ПМ-21")
        self.teacher = Teacher.objects.create(name="Иванов И.И.")
        self.subject = Subject.objects.create(name="Математика")
        self.lesson = Lesson.objects.create(
            date=date(2026, 2, 2),
            day_of_week="Понедельник",
            pair_number=1,
            group=self.group,
            teacher=self.teacher,
            subject=self.subject,
            room="101",
        )

    def test_index_ok(self):
        resp = self.client.get(reverse("schedule:index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ПМ-21")
        self.assertContains(resp, "Иванов И.И.")

    def test_group_schedule_ok(self):
        resp = self.client.get(reverse("schedule:group", args=["ПМ-21"]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Математика")

    def test_teacher_schedule_ok(self):
        resp = self.client.get(reverse("schedule:teacher", args=[self.teacher.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Математика")

    def test_unknown_group_404(self):
        resp = self.client.get(reverse("schedule:group", args=["НЕТ-99"]))
        self.assertEqual(resp.status_code, 404)


class AdminAccessTests(ScheduleTestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="pass1234")
        self.staff = User.objects.create_user(username="staff", password="pass1234", is_staff=True)

    def _login(self, user):
        self.client.login(username=user.username, password="pass1234")

    def test_anonymous_redirected_from_admin_panel(self):
        resp = self.client.get(reverse("schedule:admin_panel"))
        self.assertEqual(resp.status_code, 302)

    def test_student_cannot_open_admin_panel(self):
        self._login(self.student)
        resp = self.client.get(reverse("schedule:admin_panel"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_can_open_admin_panel(self):
        self._login(self.staff)
        resp = self.client.get(reverse("schedule:admin_panel"))
        self.assertEqual(resp.status_code, 200)

    def test_student_cannot_upload_schedule(self):
        self._login(self.student)
        resp = self.client.post(reverse("schedule:upload"))
        self.assertEqual(resp.status_code, 302)
        self.assertNotEqual(resp.url, reverse("schedule:admin_panel"))

    def test_student_cannot_delete_date(self):
        self._login(self.student)
        resp = self.client.post(reverse("schedule:delete_date"), {"date": "2026-02-02"})
        self.assertEqual(resp.status_code, 302)
        self.assertNotEqual(resp.url, reverse("schedule:admin_panel"))


class StudentAuthTests(ScheduleTestCase):
    def setUp(self):
        self.group = Group.objects.create(name="ПМ-21")
        self.invite = InviteCode.objects.create(code="INV-1", group=self.group, limit=1)

    def _register(self, username, code, password="StrongPass2026!"):
        return self.client.post(
            reverse("schedule:student_register"),
            {"username": username, "password": password, "password2": password, "invite_code": code},
        )

    def test_register_success(self):
        resp = self._register("vasya", "INV-1")
        self.assertRedirects(resp, reverse("schedule:conspect_list"))
        user = User.objects.get(username="vasya")
        self.assertEqual(user.student_profile.group, self.group)

    def test_register_weak_password_rejected(self):
        resp = self._register("petya", "INV-1", password="123")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="petya").exists())

    def test_invite_limit_enforced(self):
        resp = self._register("vasya", "INV-1")
        self.assertRedirects(resp, reverse("schedule:conspect_list"))
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.used, 1)
        self.client.logout()
        resp = self._register("petya", "INV-1")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="petya").exists())

    def test_wrong_invite_rejected(self):
        resp = self._register("petya", "BAD-CODE")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(username="petya").exists())

    def test_login_open_redirect_blocked(self):
        User.objects.create_user(username="vasya", password="secret1")
        resp = self.client.post(
            reverse("schedule:student_login"),
            {"username": "vasya", "password": "secret1", "next": "https://evil.example.com/phish"},
        )
        self.assertRedirects(resp, reverse("schedule:conspect_list"))

    def test_login_next_allowed_within_site(self):
        User.objects.create_user(username="vasya", password="secret1")
        resp = self.client.post(
            reverse("schedule:student_login"),
            {"username": "vasya", "password": "secret1", "next": "/conspects/upload/"},
        )
        self.assertRedirects(resp, "/conspects/upload/", fetch_redirect_response=False)


class ParserTests(ScheduleTestCase):
    def _make_workbook(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Понедельник"
        ws.append(["Расписание занятий на 02.02.2026"])
        ws.append([None, "ПМ-21", None, None, None, None])
        ws.append([1, "Математика", None, "Физика", "202", "101", None])
        ws.append([None, "Иванов", None, "Петров", None, None, None])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_parse_format_a(self):
        data = parse_xlsx(self._make_workbook())
        self.assertEqual(data["date"], "02.02.2026")
        self.assertEqual(data["day_of_week"], "Понедельник")
        self.assertEqual(len(data["lessons"]), 2)

        sub1 = data["lessons"][0]
        self.assertEqual(sub1["group"], "ПМ-21")
        self.assertEqual(sub1["subgroup"], 1)
        self.assertEqual(sub1["subject"], "Математика")
        self.assertEqual(sub1["teacher"], "Иванов")
        self.assertEqual(sub1["room"], "101")

        sub2 = data["lessons"][1]
        self.assertEqual(sub2["subgroup"], 2)
        self.assertEqual(sub2["subject"], "Физика")
        self.assertEqual(sub2["teacher"], "Петров")
        self.assertEqual(sub2["room"], "202")


class UploadPathTests(ScheduleTestCase):
    def test_author_name_sanitized(self):
        class FakeConspect:
            author_name = "Петров/../../../etc"
            conspect_date = type("D", (), {"subject_id": 1, "date": date(2026, 2, 2)})()

        path = conspect_upload_path(FakeConspect(), "note.pdf")
        self.assertNotIn("/../", path)
        self.assertNotIn("..", path.replace("/", "").replace(".pdf", ""))
        self.assertTrue(path.startswith("conspects/1/2026-02-02/"))
        self.assertNotIn("\\", path)
