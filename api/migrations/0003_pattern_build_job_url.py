# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-02-01 15:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_auto_20170125_1729'),
    ]

    operations = [
        migrations.AddField(
            model_name='pattern',
            name='build_job_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
