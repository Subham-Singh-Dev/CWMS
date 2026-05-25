from django.contrib import admin

from .models import ManagerProfile

@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'site')
    list_editable = ('site',)   # edit site inline from the list page.
