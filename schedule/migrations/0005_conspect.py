from django.db import migrations, models
import django.db.models.deletion
import schedule.models


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0003_feedback'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConspectSubject',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True, verbose_name='Предмет')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Предмет (конспекты)',
                'verbose_name_plural': 'Предметы (конспекты)',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ConspectDate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Дата занятия')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='dates', to='schedule.conspectsubject',
                                              verbose_name='Предмет')),
            ],
            options={
                'verbose_name': 'Дата (конспекты)',
                'verbose_name_plural': 'Даты (конспекты)',
                'ordering': ['-date'],
                'unique_together': {('subject', 'date')},
            },
        ),
        migrations.CreateModel(
            name='Conspect',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('author_name', models.CharField(max_length=100, verbose_name='Имя автора')),
                ('file', models.FileField(upload_to=schedule.models.conspect_upload_path, verbose_name='Файл')),
                ('file_type', models.CharField(
                    choices=[('conspect', 'Конспект'), ('hw', 'Домашнее задание'), ('other', 'Другое')],
                    default='conspect', max_length=10, verbose_name='Тип')),
                ('description', models.CharField(blank=True, default='', max_length=200,
                                                  verbose_name='Описание (необязательно)')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('conspect_date', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                     related_name='conspects', to='schedule.conspectdate',
                                                     verbose_name='Дата')),
            ],
            options={
                'verbose_name': 'Конспект',
                'verbose_name_plural': 'Конспекты',
                'ordering': ['author_name'],
            },
        ),
    ]
