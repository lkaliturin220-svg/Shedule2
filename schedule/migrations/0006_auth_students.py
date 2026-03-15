from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0005_conspect'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # InviteCode
        migrations.CreateModel(
            name='InviteCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='Код')),
                ('limit', models.PositiveSmallIntegerField(default=30, verbose_name='Лимит студентов')),
                ('used', models.PositiveSmallIntegerField(default=0, verbose_name='Использовано')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name='invite_codes', to='schedule.group',
                                            verbose_name='Группа')),
            ],
            options={
                'verbose_name': 'Инвайт-код',
                'verbose_name_plural': 'Инвайт-коды',
                'ordering': ['group', 'code'],
            },
        ),
        # StudentProfile
        migrations.CreateModel(
            name='StudentProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='student_profile',
                                              to=settings.AUTH_USER_MODEL,
                                              verbose_name='Пользователь')),
                ('group', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                            related_name='students', to='schedule.group',
                                            verbose_name='Группа')),
                ('invite', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                             to='schedule.invitecode',
                                             verbose_name='Инвайт-код')),
            ],
            options={
                'verbose_name': 'Профиль студента',
                'verbose_name_plural': 'Профили студентов',
            },
        ),
        # Conspect.author
        migrations.AddField(
            model_name='conspect',
            name='author',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='conspects', to=settings.AUTH_USER_MODEL,
                                    verbose_name='Аккаунт автора'),
        ),
    ]
