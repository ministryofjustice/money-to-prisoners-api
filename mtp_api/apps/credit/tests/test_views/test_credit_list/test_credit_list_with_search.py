import random

from django.utils.crypto import get_random_string

from credit.tests.test_views.test_credit_list import CreditListTestCase


class CreditListWithSearchTestCase(CreditListTestCase):
    def test_filter_search_for_prisoner_number(self):
        """
        Search for a prisoner number
        """
        search_phrase = ''
        while not search_phrase:
            credit = random.choice(self.credits)
            if credit.prisoner_number:
                search_phrase = credit.prisoner_number
        self._test_response_with_filters({
            'search': search_phrase
        })

    def test_filter_search_for_prisoner_name(self):
        """
        Search for a prisoner first name
        """
        search_phrase = ''
        while not search_phrase:
            credit = random.choice(self.credits)
            if credit.prisoner_name:
                search_phrase = credit.prisoner_name.split()[0]
        self._test_response_with_filters({
            'search': search_phrase
        })

    def test_filter_search_for_sender_name(self):
        """
        Search for a partial sender name
        """
        search_phrase = ''
        while not search_phrase:
            credit = random.choice(self.credits)
            if credit.sender_name:
                search_phrase = credit.sender_name[:2].strip()
        self._test_response_with_filters({
            'search': search_phrase
        })

    def test_filter_search_for_amount(self):
        """
        Search for a payment amount
        """
        credit = random.choice(self.credits)
        search_phrase = '£%0.2f' % (credit.amount / 100)
        self._test_response_with_filters({
            'search': search_phrase
        })

    def test_filter_search_for_amount_prefix(self):
        search_phrase = '£5'
        self._test_response_with_filters({
            'search': search_phrase
        })

    def test_empty_search(self):
        """
        Empty search causes no errors
        """
        self._test_response_with_filters({
            'search': ''
        })

    def test_search_with_no_results(self):
        """
        Search for a value that cannot exist in generated credits
        """
        response = self._test_response_with_filters({
            'search': get_random_string(
                length=20,  # too long for generated sender names
                allowed_chars='§±@£$#{}[];:<>',  # includes characters not used in generation
            )
        })
        self.assertFalse(response.data['results'])
