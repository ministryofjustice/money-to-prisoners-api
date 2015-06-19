from django.forms import Form

from rest_framework import mixins
from rest_framework import viewsets
from rest_framework import filters

from django_filters import FilterSet

from .models import Transaction
from mtp_auth.models import PrisonUserMapping
from prison.models import Prison
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


class OwnPrisonListModelMixin(object):

    def get_prison_set_for_user(self):
        try:
            return PrisonUserMapping.objects.get(user=self.request.user).prisons.all()
        except PrisonUserMapping.DoesNotExist:
            return Prison.objects.none()

    def get_queryset(self):
        qs = super(OwnPrisonListModelMixin, self).get_queryset()
        if self.request.user.is_superuser:
            return qs

        return qs.filter(prison__in=self.get_prison_set_for_user())


class TransactionView(
    OwnPrisonListModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet,
):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    filter_backends = (
        filters.DjangoFilterBackend,
        filters.OrderingFilter,
    )
    filter_class = TransactionFilter
    ordering = ('received_at',)
