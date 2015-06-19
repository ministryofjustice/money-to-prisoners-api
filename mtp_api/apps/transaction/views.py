from django.forms import Form

from rest_framework import mixins
from rest_framework import viewsets
from rest_framework import filters

from django_filters import FilterSet

from .models import Transaction
from .serializers import TransactionSerializer


class TransactionFilterForm(Form):

    def clean_upload_counter(self):
        upload_counter = self.cleaned_data.get('upload_counter')
        if upload_counter == None:
            # get the latest if 'upload_counter' param not specified
            try:
                transaction = Transaction.objects.latest('upload_counter')
                upload_counter = transaction.upload_counter
            except Transaction.DoesNotExist:
                pass
        return upload_counter


class TransactionFilter(FilterSet):

    class Meta:
        model = Transaction
        form = TransactionFilterForm
        fields = ['upload_counter']


class TransactionView(
    mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    filter_backends = (
        filters.DjangoFilterBackend,
        filters.OrderingFilter,
    )
    filter_class = TransactionFilter
    ordering = ('received_at',)
