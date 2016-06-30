from django.db import transaction

from rest_framework import serializers

from credit.signals import credit_prisons_need_updating

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

    class Meta:
        model = Prison
        fields = (
            'nomis_id',
            'general_ledger_code',
            'name',
            'region',
            'populations',
            'categories',
        )


class PrisonerLocationListSerializer(serializers.ListSerializer):

    @transaction.atomic
    def create(self, validated_data):
        locations = [
            PrisonerLocation(**item) for item in validated_data
        ]

        # delete all current records and insert new batch
        PrisonerLocation.objects.all().delete()
        objects = PrisonerLocation.objects.bulk_create(locations)

        credit_prisons_need_updating.send(sender=PrisonerLocation)

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


class PrisonerValiditySerializer(serializers.ModelSerializer):
    class Meta:
        model = PrisonerLocation
        fields = (
            'prisoner_number',
            'prisoner_dob',
        )
