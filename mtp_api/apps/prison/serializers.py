import logging

from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _
from mtp_common import nomis
import requests
from rest_framework import serializers, status
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

    @transaction.atomic
    def fetch_and_update(self):
        try:
            new_location = nomis.get_location(self.instance.prisoner_number)
            new_prison = Prison.objects.get(nomis_id=new_location['nomis_id'])
        except requests.RequestException:
            logger.error(f'Cannot look up prisoner location for {self.instance.prisoner_number} in nomis')
            return None
        except ObjectDoesNotExist:
            logger.error(f'Cannot find prison matching {new_location.nomis_id} in Prison table')
            return None
        else:
            logger.info(
                f'Moving {self.instance.prisoner_number} from {self.instance.prison.nomis_id} to {new_prison.nomis_id}'
            )
            return self.update(self.instance, {'prison': new_prison})


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
        if prisoner_location.prison.private_estate:
            # NB: balances are not known in private estate currently
            return 0

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
            msg = f'NOMIS balances for {prisoner_location.prisoner_number} is malformed: {e}'
            logger.exception(msg)
            raise ValidationError(msg)
        except requests.RequestException as e:
            # TODO I think this message is rendered on page, make it nicer
            msg = (
                f'Cannot lookup NOMIS balances for {prisoner_location.prisoner_number} in '
                f'{prisoner_location.prison.nomis_id}'
            )
            if (
                getattr(e, 'response', None) is not None and
                e.response.status_code == status.HTTP_400_BAD_REQUEST
                and update_location_on_not_found
            ):
                logger.warning(msg)
                new_location = PrisonerLocationSerializer(prisoner_location).fetch_and_update()
                if new_location:
                    return self.get_combined_account_balance(new_location, update_location_on_not_found=False)
                else:
                    # TODO add better message
                    raise ValidationError(
                        f'Could not find location for prisoner_number {prisoner_location.prisoner_number} in NOMIS'
                    )
            else:
                logger.exception(msg)
                raise ValidationError(msg)
        else:
            return sum(nomis_account_balances[account] for account in self.NOMIS_ACCOUNTS)


class PrisonBankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrisonBankAccount
        fields = '__all__'
