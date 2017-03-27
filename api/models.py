from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User


class SquadToken(models.Model):
    project = models.CharField(max_length=1024)
    token = models.CharField(max_length=64)

    def __str__(self):
        return self.project


class Pattern(models.Model):
    lava_server = models.URLField()
    lava_job_id = models.CharField(max_length=16)
    lava_job_status = models.CharField(max_length=16, null=True, blank=True)
    build_job_name = models.CharField(max_length=1024)
    build_job_url = models.URLField()
    requester = models.ForeignKey(User)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return "%s - %s (%s)" % (self.lava_job_id, self.lava_server, self.requester)


class Submission(models.Model):
    definition = models.TextField()

    # fields that should be copied to Pattern
    lava_server = models.URLField()
    build_job_name = models.CharField(max_length=1024)
    build_job_url = models.URLField()

    submitted = models.BooleanField(default=False)

    requester = models.ForeignKey(User)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.build_job_name
