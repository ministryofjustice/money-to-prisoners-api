from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class RestrictedUserCreationForm(UserCreationForm):
    error_messages = {
        'non_unique_username': _('That username already exists'),
        'password_mismatch': _('The two password fields didn’t match'),
    }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            try:
                User.objects.get_by_natural_key(username)
                raise ValidationError(self.error_messages['non_unique_username'],
                                      code='non_unique_username')
            except User.DoesNotExist:
                pass
        return username


class RestrictedUserChangeForm(UserChangeForm):
    error_messages = {
        'non_unique_username': _('That username already exists'),
        'non_unique_email': _('That email address already exists'),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ['first_name', 'last_name', 'email']:
            field = self.fields[field_name]
            field.required = True
            field.widget.is_required = True

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            try:
                user = User.objects.get_by_natural_key(username)
                if user.pk != self.instance.pk:
                    raise ValidationError(self.error_messages['non_unique_username'],
                                          code='non_unique_username')
            except User.DoesNotExist:
                pass
        return username

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
