from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as format_date
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from core.admin import add_short_description
from notification.models import (
    Subscription, Parameter, Event, EventCredit, EventDisbursement
)
from transaction.utils import format_amount


class ParameterAdminInline(admin.StackedInline):
    model = Parameter
    extra = 0


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('rule', 'user', 'start')
    inlines = (ParameterAdminInline,)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('rule', 'description')


@admin.register(EventCredit)
class EventCreditAdmin(admin.ModelAdmin):
    list_display = ('event', 'credit',)
    exclude = ('credit', 'event',)
    readonly_fields = ('credit_link', 'event_link',)

    @add_short_description(_('credit'))
    def credit_link(self, instance):
        link = reverse('admin:credit_credit_change', args=(instance.credit.pk,))
        description = '%(amount)s %(status)s, %(date)s' % {
            'amount': format_amount(instance.credit.amount),
            'status': instance.credit.resolution,
            'date': format_date(timezone.localtime(instance.credit.created), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)

    @add_short_description(_('event'))
    def event_link(self, instance):
        link = reverse('admin:notification_event_change', args=(instance.event.pk,))
        description = '%(date)s' % {
            'date': format_date(timezone.localtime(instance.event.created), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)


@admin.register(EventDisbursement)
class EventDisbursementAdmin(admin.ModelAdmin):
    list_display = ('event', 'disbursement',)
    exclude = ('disbursement', 'event',)
    readonly_fields = ('disbursement_link', 'event_link',)

    @add_short_description(_('disbursement'))
    def disbursement_link(self, instance):
        link = reverse('admin:disbursement_disbursement_change', args=(instance.disbursement.pk,))
        description = '%(amount)s %(status)s, %(date)s' % {
            'amount': format_amount(instance.disbursement.amount),
            'status': instance.disbursement.resolution,
            'date': format_date(timezone.localtime(instance.disbursement.created), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)

    @add_short_description(_('event'))
    def event_link(self, instance):
        link = reverse('admin:notification_event_change', args=(instance.event.pk,))
        description = '%(date)s' % {
            'date': format_date(timezone.localtime(instance.event.created), 'd/m/Y'),
        }
        return format_html('<a href="{}">{}</a>', link, description)
