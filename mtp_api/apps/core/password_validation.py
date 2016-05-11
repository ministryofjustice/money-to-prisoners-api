from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class MinimumLengthValidator(password_validation.MinimumLengthValidator):
    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError as e:
            if e.code == 'password_too_short':
                raise ValidationError(_('This password is too weak '
                                        '(use at least %(min_length)d characters)'),
                                      code=e.code, params=e.params)
            raise


class UserAttributeSimilarityValidator(password_validation.UserAttributeSimilarityValidator):
    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError as e:
            if e.code == 'password_too_similar':
                raise ValidationError(_('This password is too weak '
                                        '(similar to %(verbose_name)s)'),
                                      code=e.code, params=e.params)
            raise


class CommonPasswordValidator(password_validation.CommonPasswordValidator):
    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError as e:
            if e.code == 'password_too_common':
                raise ValidationError(_('This password is too weak '
                                        '(too common)'),
                                      code=e.code)
            raise


class NumericPasswordValidator(password_validation.NumericPasswordValidator):
    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError as e:
            if e.code == 'password_entirely_numeric':
                raise ValidationError(_('This password is too weak '
                                        '(use numbers and letters)'),
                                      code=e.code)
            raise
