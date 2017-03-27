from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from unittest.mock import patch
from api.models import Pattern, Submission


class ApiTests(APITestCase):

    def setUp(self):
        user = User.objects.create_superuser('test', 'email@test.com', 'test')
        self.client.force_authenticate(user=user)

    def test_pattern(self):
        self.client.post('/api/pattern/', {
            'lava_server': 'https://validation.linaro.org/RPC2',
            'lava_job_id': '99999',
            'build_job_name': 'foo/bar/v1.0.1-55',
            'build_job_url': 'http://example.com/foo/bar/v1.0.1-55',
        })
        self.assertIsNotNone(Pattern.objects.get(lava_job_id='99999'))

    @patch('api.tasks.submit_to_lava.delay')
    def test_submission(self, schedule_submission):
        self.client.post('/api/submission/', {
            'definition': 'foo: 1\n',
            'lava_server': 'https://validation.linaro.org/RPC2',
            'build_job_name': 'foo/bar/v1.0.1-55',
            'build_job_url': 'http://example.com/foo/bar/v1.0.1-55',
        })
        submission = Submission.objects.get(build_job_name='foo/bar/v1.0.1-55')
        schedule_submission.assert_called_with(submission.id)
