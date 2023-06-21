from rest_framework.serializers import ModelSerializer

from performance.models import PerformanceData


class PerformanceDataSerializer(ModelSerializer):
    class Meta:
        model = PerformanceData
        fields = '__all__'
