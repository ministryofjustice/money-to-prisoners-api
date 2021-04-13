import logging

from django.db import transaction
from django.utils.translation import gettext as _
from mtp_common import nomis
import requests
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError

from prison.models import PrisonerLocation, Prison, Category, Population, PrisonBankAccount, PrisonerBalance
from prison.utils import fetch_prisoner_location_from_nomis

logger = logging.getLogger('mtp')

TOLERATED_NOMIS_ERROR_CODES = (
    status.HTTP_404_NOT_FOUND,
    status.HTTP_500_INTERNAL_SERVER_ERROR,
    status.HTTP_502_BAD_GATEWAY,
    status.HTTP_503_SERVICE_UNAVAILABLE,
    status.HTTP_504_GATEWAY_TIMEOUT,
    status.HTTP_507_INSUFFICIENT_STORAGE
)


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
    NOMIS_ACCOUNTS = {'cash', 'spends', 'savings'}
    combined_account_balance = serializers.SerializerMethodField()

    def get_combined_account_balance(self, prisoner_location: PrisonerLocation, update_location_on_not_found=True):
        if not prisoner_location.prison.use_nomis_for_balances:
            # for establishments that do not use nomis for prisoner monies, check internal records instead
            try:
                balance_from_prison_without_nomis = PrisonerBalance.objects.get(
                    prisoner_number=prisoner_location.prisoner_number,
                    prison=prisoner_location.prison.nomis_id,
                )
                return balance_from_prison_without_nomis.amount
            except PrisonerBalance.DoesNotExist:
                # balances will only be provided for people above a certain threshold
                # therefore a missing balance actually indicates a low (and acceptable) balance
                return 0

        # otherwise, check NOMIS each time
        try:
            nomis_account_balances = nomis.get_account_balances(
                prisoner_location.prison.nomis_id,
                prisoner_location.prisoner_number,
            )
            assert set(nomis_account_balances.keys()) == self.NOMIS_ACCOUNTS, 'response keys differ from expected'
            assert all(
                isinstance(nomis_account_balances[account], int) and nomis_account_balances[account] >= 0
                for account in self.NOMIS_ACCOUNTS
            ), 'not all response values are natural ints'
        except AssertionError as e:
            logger.exception(
                'NOMIS balances for prisoner is malformed',
                {
                    'prisoner_number': prisoner_location.prisoner_number,
                    'exception': e
                }
            )
            raise ValidationError(f'NOMIS balances for {prisoner_location.prisoner_number} is malformed: {e}')
        except requests.RequestException as e:
            if (
                getattr(e, 'response', None) is not None
                and e.response.status_code == status.HTTP_400_BAD_REQUEST
                and update_location_on_not_found
            ):
                logger.warning(
                    'Cannot lookup NOMIS balances for prisoner in given prison',
                    {
                        'prisoner_number': prisoner_location.prisoner_number,
                        'prison_nomis_id': prisoner_location.prison.nomis_id,
                        'exception': e
                    }
                )
                new_location = fetch_prisoner_location_from_nomis(prisoner_location)
                if new_location:
                    return self.get_combined_account_balance(new_location, update_location_on_not_found=False)
                else:
                    raise ValidationError(
                        f'Could not find location for prisoner_number {prisoner_location.prisoner_number} in NOMIS'
                    )
            elif (
                getattr(e, 'response', None) is not None
                and e.response.status_code in TOLERATED_NOMIS_ERROR_CODES
            ):
                # We want to explicitly allow through in the case of a NOMIS outage
                logger.warning(
                    'Tried to contact nomis to fetch balance for prisoner but received '
                    f'HTTP error code {e.response.status_code}. Allowing payment to continue without balance check',
                    {'prisoner_number': prisoner_location.prisoner_number}
                )
                return 0
            else:
                logger.exception(
                    'Cannot lookup NOMIS balances for prisoner in given prison',
                    {
                        'prisoner_number': prisoner_location.prisoner_number,
                        'prison_nomis_id': prisoner_location.prison.nomis_id,
                        'exception': e
                    }
                )
                raise ValidationError(
                    (
                        f'Cannot lookup NOMIS balances for {prisoner_location.prisoner_number} in '
                        f'{prisoner_location.prison.nomis_id}'
                    )
                )
        else:
            return sum(nomis_account_balances[account] for account in self.NOMIS_ACCOUNTS)


class PrisonBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrisonBankAccount
        fields = '__all__'
