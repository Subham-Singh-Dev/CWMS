from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin interface for viewing audit logs"""
    list_display = ['timestamp', 'username', 'activity', 'action', 'entity_name', 'status']
    list_filter = ['activity', 'action', 'status', 'timestamp', 'user_role']
    search_fields = ['username', 'entity_name', 'details']
    readonly_fields = ['timestamp', 'user', 'username', 'user_role', 'activity', 'action', 'entity_type', 'entity_id', 'entity_name', 'details', 'old_values', 'new_values', 'ip_address', 'status', 'error_message']
    date_hierarchy = 'timestamp'
    
    def has_add_permission(self, request):
        """Prevent manual addition of audit logs"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Only superuser can delete audit logs"""
        return request.user.is_superuser

