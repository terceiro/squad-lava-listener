from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from api.models import Pattern
from api.tasks import match_pattern


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            'LAVASERVER',
        )
        parser.add_argument(
            'JOBID',
        )
        parser.add_argument(
            'BUILDID',
        )
        parser.add_argument(
            'PROJECT',
        )

    def handle(self, *args, **options):
        server = options['LAVASERVER']
        job_id = options['JOBID']
        build = options['BUILDID']
        project = options['PROJECT']

        pattern = Pattern.objects.create(
            lava_server=server,
            lava_job_id=job_id,
            lava_job_status='Complete',
            build_job_name= project + '/' + build,
            build_job_url='https://www.example.com/',  # FIXME
            requester=User.objects.last(),
        )

        data = {
            "job": job_id,
            "status": 'Complete',
            "pipeline": True,
            "description": build,
        }

        match_pattern(None, None, None, data)
