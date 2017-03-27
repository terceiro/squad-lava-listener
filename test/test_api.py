from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from api.models import Pattern


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
