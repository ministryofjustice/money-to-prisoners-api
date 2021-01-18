from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.serializers import BasicUserSerializer
from disbursement.models import Disbursement, Log, Comment
from disbursement.signals import disbursement_created, disbursement_edited
from mtp_auth.models import PrisonUserMapping
from prison.models import PrisonerLocation, Prison


class PrisonerInPrisonValidator:
    def __call__(self, data):
        if 'prisoner_number' in data:
            prisoner_number = data.get('prisoner_number')
            prison = data.get('prison')

            try:
                PrisonerLocation.objects.get(
                    prisoner_number=prisoner_number,
                    prison=prison,
                    active=True
                )
            except PrisonerLocation.DoesNotExist:
                raise serializers.ValidationError(
                    _('Prisoner %(prisoner_number)s is not in %(prison)s') %
                    {'prisoner_number': prisoner_number, 'prison': prison}
                )


class PrisonPermittedValidator():
    def set_context(self, serializer):
        self.user = serializer.context['request'].user

    def __call__(self, value):
        if (
            value not in
            PrisonUserMapping.objects.get_prison_set_for_user(self.user)
        ):
            raise serializers.ValidationError(
                _('Cannot create a disbursement for this prison')
            )


class LogSerializer(serializers.ModelSerializer):
    user = BasicUserSerializer()

    class Meta:
        model = Log
        fields = (
            'user',
            'action',
            'created',
        )


class CommentSerializer(serializers.ModelSerializer):
    user_full_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        ref_name = 'Disbursement Comment'
        model = Comment
        read_only = ('user',)
        fields = ('disbursement', 'user', 'user_full_name', 'comment', 'category')

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)

    def get_user_full_name(self, obj):
        return obj.user.get_full_name() if obj.user else None


class DisbursementSerializer(serializers.ModelSerializer):
    log_set = LogSerializer(many=True, required=False)
    comments = CommentSerializer(many=True, required=False)
    prison = serializers.PrimaryKeyRelatedField(
        queryset=Prison.objects.all(),
        validators=[PrisonPermittedValidator()]
    )
    prison_name = serializers.SerializerMethodField()
    prisoner_name = serializers.CharField(required=False)
    resolution = serializers.CharField(read_only=True)

    class Meta:
        model = Disbursement
        fields = '__all__'
        validators = [PrisonerInPrisonValidator()]

    @atomic
    def create(self, validated_data):
        validated_data['prisoner_name'] = PrisonerLocation.objects.get(
            prisoner_number=validated_data['prisoner_number'],
            active=True
        ).prisoner_name
        new_disbursement = super().create(validated_data)
        disbursement_created.send(
            sender=Disbursement,
            disbursement=new_disbursement,
            by_user=self.context['request'].user
        )
        return new_disbursement

    @atomic
    def update(self, instance, validated_data):
        if 'prisoner_number' in validated_data:
            validated_data['prisoner_name'] = PrisonerLocation.objects.get(
                prisoner_number=validated_data['prisoner_number'],
                active=True
            ).prisoner_name
        updated_disbursement = super().update(instance, validated_data)
        if validated_data:
            disbursement_edited.send(
                sender=Disbursement,
                disbursement=updated_disbursement,
                by_user=self.context['request'].user
            )
        return updated_disbursement

    @classmethod
    def get_prison_name(cls, obj):
        try:
            return Prison.objects.get(pk=obj.prison_id).name
        except Prison.DoesNotExist:
            return None


class DisbursementIdsSerializer(serializers.Serializer):
    disbursement_ids = serializers.ListField(child=serializers.IntegerField())


class DisbursementConfirmationSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
    nomis_transaction_id = serializers.CharField(required=False, allow_null=True)
