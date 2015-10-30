from django.contrib import admin

from .models import File, FileType, Balance

admin.site.register(File)
admin.site.register(FileType)
admin.site.register(Balance)
