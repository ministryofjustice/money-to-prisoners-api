from django.db.models import Max

from rest_framework import serializers

from .models import PrisonerLocation


class PrisonerLocationListSerializer(serializers.ListSerializer):

    def get_latest_upload_counter(self):
        result = PrisonerLocation.objects.all().aggregate(max=Max('upload_counter'))
        return result['max'] or 0

    def create(self, validated_data):
        # NOTE: this can cause race conditions and can be fixed but do we care?
        # Not likely to happen
        next_upload_counter = self.get_latest_upload_counter() + 1

        locations = [
            PrisonerLocation(upload_counter=next_upload_counter, **item) for item in validated_data
        ]
        return PrisonerLocation.objects.bulk_create(locations)


class PrisonerLocationSerializer(serializers.ModelSerializer):

    class Meta:
        model = PrisonerLocation
        list_serializer_class = PrisonerLocationListSerializer
        fields = (
            'prisoner_number',
            'prisoner_dob',
            'prison',
        )
