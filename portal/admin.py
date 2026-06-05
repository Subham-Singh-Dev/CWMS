from django.contrib import admin
from .models import BrandSettings
from .models import ManagerProfile

@admin.register(ManagerProfile)
class ManagerProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'site')
    list_editable = ('site',)   # edit site inline from the list page.

@admin.register(BrandSettings)
class BrandSettingsAdmin(admin.ModelAdmin):
    # Prevents adding a second settings row if one already exists
    def has_add_permission(self, request):
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)
