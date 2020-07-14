import logging

from django.db import transaction
from django.utils.translation import gettext as _
from mtp_common import nomis
import requests
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from prison.models import PrisonerLocation, Prison, Category, Population, PrisonBankAccount

logger = logging.getLogger('mtp')


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

    # TODO Deduplicate this and security.serializers.PrisonSerializer
    # so drf-yasg stops complaining about serializer namespace collisions
    # without custom ref name
    class Meta:
        ref_name = 'Prison Prison'
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
            'private_estate',
            'cms_establishment_code',
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


class PrisonerAccountBalanceSerializer(serializers.Serializer):
    combined_account_balance = serializers.SerializerMethodField()

    def get_combined_account_balance(self, prisoner_location: PrisonerLocation):
        if prisoner_location.prison.private_estate:
            # NB: balances are not known in private estate currently
            return 0

        try:
            nomis_account_balances = nomis.get_account_balances(
                prisoner_location.prison.nomis_id,
                prisoner_location.prisoner_number,
            )
            return (
                nomis_account_balances['cash'] +
                nomis_account_balances['spends'] +
                nomis_account_balances['savings']
            )
        except KeyError:
            msg = f'NOMIS balances for {prisoner_location.prisoner_number} is malformed'
            logger.exception(msg)
            raise ValidationError(msg)
        except requests.RequestException:
            msg = f'Cannot lookup NOMIS balances for {prisoner_location.prisoner_number}'
            logger.exception(msg)
            raise ValidationError(msg)


class PrisonBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrisonBankAccount
        fields = '__all__'
