# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import hashlib

from django.db import models, migrations


def calculate_prisoner_hash(location):
    original = '{number}_{dob}'.format(
        number=location.prisoner_number.lower(),
        dob=location.prisoner_dob.strftime('%d/%m/%Y')
    )
    hash_object = hashlib.sha256(original.encode())
    return hash_object.hexdigest()


def populate_prisoner_hash(apps, schema_editor):
    PrisonerLocation = apps.get_model("prison", "PrisonerLocation")

    for location in PrisonerLocation.objects.all():
        location.prisoner_hash = calculate_prisoner_hash(location)
        location.save(update_fields=['prisoner_hash'])


class Migration(migrations.Migration):

    dependencies = [
        ('prison', '0004_prisonerlocation_prisoner_hash'),
    ]

    operations = [
        migrations.RunPython(populate_prisoner_hash),
    ]
