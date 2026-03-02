from django.contrib import admin
from django.contrib.auth.models import User
from django.db import transaction
from django.db import models  # <--- THIS WAS MISSING
from django.db.models import Max
from django.db.models.functions import Cast, Substr
import secrets

from .models import Employee, Role

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'overtime_rate_per_hour', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    exclude = ('user',)
    list_display = ('name', 'role', 'phone_number', 'get_system_id', 'is_active')
    search_fields = ('name', 'phone_number', 'user__username')
    list_filter = ('is_active', 'role')

    def get_system_id(self, obj):
        return obj.user.username if obj.user else "-"
    get_system_id.short_description = 'System ID'

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            # =========================
            # CREATE (New Employee)
            # =========================
            if not obj.pk:
                # 1. Robust ID Generation
                last_num = (
                    User.objects
                    .filter(username__startswith="EMP")
                    .annotate(
                        # Now 'models' is defined, so this line will work
                        num=Cast(Substr('username', 4), models.IntegerField())
                    )
                    .aggregate(max_num=Max('num'))
                    .get('max_num')
                ) or 0

                new_id = last_num + 1
                username = f"EMP{new_id:05d}"

                # 2. Secure Password Generation
                temp_password = secrets.token_urlsafe(8)

                # 3. Create User
                user = User.objects.create_user(
                    username=username,
                    password=temp_password,
                    is_active=obj.is_active
                )

                # 4. Link & Save
                obj.user = user
                super().save_model(request, obj, form, change)

                # 5. Success Message (With Password)
                self.message_user(
                    request,
                    f"✅ SUCCESS: Employee '{obj.name}' created.\n"
                    f"🆔 System ID: {username}\n"
                    f"🔑 Temporary Password: {temp_password}\n"
                    f"(Please write this down; it will not be shown again.)",
                    level='success'
                )

            # =========================
            # UPDATE (Existing Employee)
            # =========================
            else:
                super().save_model(request, obj, form, change)

                # Sync Active Status
                if obj.user:
                    if obj.user.is_active != obj.is_active:
                        obj.user.is_active = obj.is_active
                        obj.user.save(update_fields=['is_active'])
