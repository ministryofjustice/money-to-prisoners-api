
from rest_framework.test import APITestCase


class TestSwagger(APITestCase):

    def test_get(self):
        response = self.client.get(
            '/swagger/?format=openapi',
            follow=True
        )
        self.assertEqual(response.status_code, 200)
