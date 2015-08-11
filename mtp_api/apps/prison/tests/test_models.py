from model_mommy import mommy

from django.test import TestCase

from prison.models import Prison, PrisonerLocation

from .utils import random_prisoner_number, random_prisoner_dob


class PrisonerHashTestCase(TestCase):
    fixtures = [
        'test_prisons.json'
    ]

    def setUp(self):
        super(PrisonerHashTestCase, self).setUp()
        self.user = mommy.make_recipe('mtp_auth.tests.basic_user')

        self.pl = PrisonerLocation(
            created_by=self.user,
            prisoner_number=random_prisoner_number(),
            prisoner_dob=random_prisoner_dob(),
            prison=Prison.objects.order_by('?').first()
        )

    def test_save_new(self):
        self.assertEqual(self.pl.prisoner_hash, '')
        self.pl.save()
        self.assertNotEqual(self.pl.prisoner_hash, '')

    def test_save_existing(self):
        """
        Tests that changing the prison of an existing prisoner
        location won't change the prisoner_hash.
        """
        self.pl.save()

        prisoner_hash = self.pl.prisoner_hash

        self.pl.prison = Prison.objects.order_by('?').first()
        self.pl.save()
        self.assertEqual(self.pl.prisoner_hash, prisoner_hash)

    def test_save_after_updating_prisoner_number(self):
        """
        Tests that changing the prison_number of an existing prisoner
        location changes the prisoner_hash.
        """
        self.pl.save()

        prisoner_hash = self.pl.prisoner_hash

        self.pl.prisoner_number = random_prisoner_number()
        self.pl.save()
        self.assertNotEqual(self.pl.prisoner_hash, prisoner_hash)

    def test_save_after_updating_prisoner_dob(self):
        """
        Tests that changing the prison_dob of an existing prisoner
        location changes the prisoner_hash.
        """
        self.pl.save()

        prisoner_hash = self.pl.prisoner_hash

        self.pl.prisoner_dob = random_prisoner_dob()
        self.pl.save()
        self.assertNotEqual(self.pl.prisoner_hash, prisoner_hash)
