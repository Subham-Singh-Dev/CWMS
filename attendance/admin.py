from django.contrib import admin
from .models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'status', 'overtime_hours', 'marked_at')
    list_filter = ('status', 'date')
    search_fields = ('employee__name',)
    readonly_fields = ('marked_at',)
