from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class RestrictedUserChangeForm(UserChangeForm):
    error_messages = {
        'non_unique_email': _('A user with that email address already exists'),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ['first_name', 'last_name', 'email']:
            field = self.fields[field_name]
            field.required = True
            field.widget.is_required = True

    def clean_email(self):
        email = self.cleaned_data.get('email')

        if email:
            queryset = User.objects.filter(email=email)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.count():
                raise ValidationError(self.error_messages['non_unique_email'],
                                      code='non_unique_email')

        return email
