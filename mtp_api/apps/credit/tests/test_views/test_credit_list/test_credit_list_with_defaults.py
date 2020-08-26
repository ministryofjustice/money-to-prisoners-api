import random

from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithDefaultsTestCase(CreditListTestCase):
    def test_returns_all_credits(self):
        """
        Returns all credits attached to all the prisons that
        the logged-in user can manage.
        """
        self._test_response_with_filters({})

    def test_filter_by_sender_name(self):
        search = ''
        while not search:
            credit = random.choice(self.credits)
            if credit.sender_name:
                search = credit.sender_name[:-4].strip()
        self._test_response_with_filters({
            'sender_name': search
        })

    def test_filter_by_prisoner_name(self):
        search = ''
        while not search:
            credit = random.choice(self.credits)
            if credit.prisoner_name:
                search = credit.prisoner_name[:-4].strip()
        self._test_response_with_filters({
            'prisoner_name': search
        })

    def test_filter_by_prison_region(self):
        search = ''
        while not search:
            credit = random.choice(self.credits)
            if credit.prison:
                search = credit.prison.region
        self._test_response_with_filters({
            'prison_region': search
        })

    def test_filter_by_prison_population(self):
        search = ''
        while not search:
            credit = random.choice(self.credits)
            if credit.prison:
                search = credit.prison.populations.first().name
        self._test_response_with_filters({
            'prison_population': search
        })

    def test_filter_by_prison_category(self):
        search = ''
        while not search:
            credit = random.choice(self.credits)
            if credit.prison:
                search = credit.prison.categories.first().name
        self._test_response_with_filters({
            'prison_category': search
        })

    def test_filter_by_multiple_prison_categories(self):
        search = []
        while len(search) < 2:
            credit = random.choice(self.credits)
            if credit.prison and credit.prison.categories.first().name not in search:
                search.append(credit.prison.categories.first().name)
        self._test_response_with_filters({
            'prison_category': search
        })

    def test_filter_by_pks(self):
        search = []
        while len(search) < 2:
            credit = random.choice(self.credits)
            if credit.pk not in search:
                search.append(credit.pk)
        self._test_response_with_filters({
            'pk': search
        })

    def test_exclude_credit__in(self):
        credits = self.credits.copy()
        credit_to_exclude = credits.pop(0)
        self._test_response_with_filters({
            'exclude_credit__in': [credit_to_exclude.id]
        })
