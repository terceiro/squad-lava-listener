import json
import logging
import multiprocessing
import signal
import zmq

from zmq.utils.strtypes import u

from django.core.management.base import BaseCommand

from listener.models import LavaListener
from api.tasks import match_pattern

logger = logging.getLogger(__name__)

class ZMQDaemon(multiprocessing.Process):

    def set_listener(self, listener):
        self.listener = listener

    def setup(self):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.setsockopt_string(zmq.SUBSCRIBE, unicode(self.listener.topic_name))
        self.socket.connect(self.listener.publisher_address)
        self.run_forever = True

    def run(self):
        self.setup()
        logger.info("starting listener process: %s" % self.listener)
        while True:
            try:
                logger.debug("waiting for the message")
                message = self.socket.recv_multipart()
                logger.debug("received message")
                (topic, uuid, dt, username, data) = (u(m) for m in message[:])
                logger.debug(topic)
                logger.debug(data)
                match_pattern.delay(uuid, dt, username, json.loads(data))
            except Exception as e:
                logger.error(e)
                pass


class Command(BaseCommand):
    def handle(self, **kwargs):
        # only start listeners that aren't already running
        listeners = LavaListener.all()

        default_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        zmqd_ref_array = []
        for listener in listeners:
            logger.info("starting %s" % listener)
            zmqd = ZMQDaemon()
            zmqd.set_listener(listener)
            zmqd.start()
            zmqd_ref_array.append(zmqd)
        signal.signal(signal.SIGINT, default_handler)
        signal.signal(signal.SIGTERM, lambda signum, frame: {})
        try:
            signal.pause()
        except KeyboardInterrupt:
            pass

        for zmqd in zmqd_ref_array:
            zmqd.terminate()
            zmqd.join()


