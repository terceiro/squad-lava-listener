from __future__ import unicode_literals

from django.db import models

class LavaListener(models.Model):
    name = models.CharField(max_length=128)
    publisher_address = models.CharField(max_length=1024)
    topic_name = models.CharField(max_length=1024)
    pid = models.CharField(max_length=8, null=True, blank=True)


    def __str__(self):
        return self.name
