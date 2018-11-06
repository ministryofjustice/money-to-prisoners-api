from django.contrib import admin

from notification.models import Subscription, Parameter, Event


class ParameterAdminInline(admin.StackedInline):
    model = Parameter
    extra = 0


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('rule', 'user', 'start')
    inlines = (ParameterAdminInline,)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('rule', 'user', 'ref_number', 'description')
