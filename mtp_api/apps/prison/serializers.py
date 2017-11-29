from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers

from .models import PrisonerLocation, Prison, Category, Population


class PopulationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Population
        fields = ('name', 'description')


class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Category
        fields = ('name', 'description')


class PrisonSerializer(serializers.ModelSerializer):
    populations = PopulationSerializer(many=True)
    categories = CategorySerializer(many=True)
    short_name = serializers.CharField(read_only=True)

    class Meta:
        model = Prison
        fields = (
            'nomis_id',
            'general_ledger_code',
            'name',
            'short_name',
            'region',
            'populations',
            'categories',
            'pre_approval_required',
        )


class PrisonerLocationListSerializer(serializers.ListSerializer):

    @transaction.atomic
    def create(self, validated_data):
        locations = [
            PrisonerLocation(**item) for item in validated_data
        ]
        objects = PrisonerLocation.objects.bulk_create(locations)
        return objects


class PrisonerLocationSerializer(serializers.ModelSerializer):

    class Meta:
        model = PrisonerLocation
        list_serializer_class = PrisonerLocationListSerializer
        fields = (
            'prisoner_name',
            'prisoner_number',
            'prisoner_dob',
            'prison',
        )
        extra_kwargs = {
            'prison': {
                'error_messages': {
                    'does_not_exist': _('No prison found with code "{pk_value}"')
                }
            }
        }


class PrisonerValiditySerializer(serializers.ModelSerializer):
    class Meta:
        model = PrisonerLocation
        fields = (
            'prisoner_number',
            'prisoner_dob',
        )
