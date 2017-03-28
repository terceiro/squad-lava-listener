from django.contrib.auth.models import User
from django.test import TestCase
from unittest.mock import patch


from api.models import Pattern, Submission
from api.tasks import submit_to_lava

class LavaSubmissionTest(TestCase):

    @patch('api.testminer.GenericLavaTestSystem.submit', return_value=7777)
    def test_submit_to_lava(self, actual_submit):
        user = User.objects.create_superuser('test', 'email@test.com', 'test')
        data = {
            'definition': 'foo: 1\n',
            'lava_server': 'https://host.example.com/RPC2',
            'build_job_name': 'foo/bar/v1.0.1-55',
            'build_job_url': 'http://example.com/foo/bar/v1.0.1-55',
            'requester_id': user.id,
        }
        submission = Submission.objects.create(**data)
        submit_to_lava.apply(args=[submission.id])

        # was submitted to LAVA
        actual_submit.assert_called_with(submission.definition)

        # a corresponding Pattern was created
        self.assertIsNotNone(Pattern.objects.get(
            lava_server=submission.lava_server,
            lava_job_id=7777,
            build_job_name=submission.build_job_name,
            build_job_url=submission.build_job_url,
        ))

        submission.refresh_from_db()
        self.assertTrue(submission.submitted)
