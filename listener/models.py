from __future__ import unicode_literals

from django.conf import settings

class LavaListener():

    __all__ = None

    name = None
    publisher_address = None
    topic_name = None

    def __init__(self, config):
        self.name = config['name']
        self.publisher_address = config['zmq_endpoint']
        self.topic_name = config['zmq_topic']

    @classmethod
    def all(cls):
        if cls.__all__ is None:
            cls.__all__ = [cls(entry) for entry in settings.LAVA_LISTENERS]
        return cls.__all__

    def __str__(self):
        return self.name
