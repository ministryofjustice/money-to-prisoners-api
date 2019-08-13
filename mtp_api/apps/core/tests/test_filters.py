from unittest import mock

from django.db.models import Q
from django.test import SimpleTestCase

from django_filters.constants import EMPTY_VALUES

from core.filters import PostcodeFilter, SplitTextInMultipleFieldsFilter


class SplitTextInMultipleFieldsFilterTestCase(SimpleTestCase):
    """
    Tests for SplitTextInMultipleFieldsFilter.
    """

    def test_no_field_names_raises_exception(self):
        """
        Test that an exception is raised if field_names is not passed in.
        """
        with self.assertRaises(ValueError):
            SplitTextInMultipleFieldsFilter()

    def test_filtering(self):
        """
        Test that the filtering logic generates the expected call to .filter().
        """
        qs = mock.Mock(spec=['filter'])
        f = SplitTextInMultipleFieldsFilter(
            field_names=('field1', 'field2'),
        )

        result = f.filter(qs, 'term1 term2')
        qs.filter.assert_called_once_with(
            Q(field1__exact='term1') | Q(field2__exact='term1'),
            Q(field1__exact='term2') | Q(field2__exact='term2'),
        )
        self.assertNotEqual(qs, result)

    def test_filtering_exclude(self):
        """
        Test that the filtering logic generates the expected call to .exclude()
        if the exclude=True argument is passed in.
        """
        qs = mock.Mock(spec=['exclude'])
        f = SplitTextInMultipleFieldsFilter(
            field_names=('field1', 'field2'),
            exclude=True,
        )

        result = f.filter(qs, 'term1 term2')
        qs.exclude.assert_called_once_with(
            Q(field1__exact='term1') | Q(field2__exact='term1'),
            Q(field1__exact='term2') | Q(field2__exact='term2'),
        )
        self.assertNotEqual(qs, result)

    def test_filtering_skipped_with_blank_value(self):
        """
        Test that no change to the qs is made if the value is empty.
        """
        for value in EMPTY_VALUES:
            qs = mock.Mock()
            f = SplitTextInMultipleFieldsFilter(
                field_names=('field1', 'field2'),
            )

            result = f.filter(qs, value)
            self.assertListEqual(qs.method_calls, [])
            self.assertEqual(qs, result)

    def test_filtering_lookup_expr(self):
        """
        Test that if a lookup_expr argument is passed in, its value is used to construct the qs.
        """
        qs = mock.Mock(spec=['filter'])
        f = SplitTextInMultipleFieldsFilter(
            field_names=('field1', 'field2'),
            lookup_expr='icontains',
        )

        result = f.filter(qs, 'term1 term2')
        qs.filter.assert_called_once_with(
            Q(field1__icontains='term1') | Q(field2__icontains='term1'),
            Q(field1__icontains='term2') | Q(field2__icontains='term2'),
        )
        self.assertNotEqual(qs, result)


class PostcodeFilterTestcase(SimpleTestCase):
    """
    Tests for the PostcodeFilter.
    """

    def test_overriding_lookup_expr_raises_exception(self):
        """
        Test that an exception is raised if lookup_expr is passed in.
        """
        with self.assertRaises(ValueError):
            PostcodeFilter(field_name='field', lookup_expr='iexact')

    def test_filtering(self):
        """
        Test that the filtering logic generates the expected call to .filter().
        """
        qs = mock.Mock(spec=['filter'])
        f = PostcodeFilter(field_name='field')

        result = f.filter(qs, 'sw1a 1aa')
        qs.filter.assert_called_once_with(
            field__iregex='s\\s*w\\s*1\\s*a\\s*1\\s*a\\s*a',
        )
        self.assertNotEqual(qs, result)

    def test_filtering_exclude(self):
        """
        Test that the filtering logic generates the expected call to .exclude()
        if the exclude=True argument is passed in.
        """
        qs = mock.Mock(spec=['exclude'])
        f = PostcodeFilter(field_name='field', exclude=True)

        result = f.filter(qs, 'sw1a 1aa')
        qs.exclude.assert_called_once_with(
            field__iregex='s\\s*w\\s*1\\s*a\\s*1\\s*a\\s*a',
        )
        self.assertNotEqual(qs, result)

    def test_filtering_skipped_with_blank_value(self):
        """
        Test that no change to the qs is made if the value is empty.
        """
        for value in EMPTY_VALUES:
            qs = mock.Mock()
            f = PostcodeFilter(field_name='field')

            result = f.filter(qs, value)
            self.assertListEqual(qs.method_calls, [])
            self.assertEqual(qs, result)
