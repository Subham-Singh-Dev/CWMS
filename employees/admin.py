"""
Module: employees.admin
App: employees
Purpose: Django admin configuration for roles and employee master records.
Dependencies: employees.models, auth User, transactional save behavior.
Author note: Admin create flow auto-generates deterministic EMP IDs and one-time temporary passwords.
"""

from django.contrib import admin
from django import forms
from django.contrib.auth.models import User
from django.db import transaction
from django.db import models  # <--- THIS WAS MISSING
from django.db.models import Max
from django.db.models.functions import Cast, Substr
import secrets

from .models import Employee, Role


class EmployeeAdminForm(forms.ModelForm):
    """Admin form with classification validation for statutory flags."""
    class Meta:
        """Bind admin form metadata to Employee model and managed fields."""
        model = Employee
        exclude = ('user',)

    def clean(self):
        """Block incompatible PF/ESIC flags when employment type is LOCAL."""
        cleaned_data = super().clean()
        if cleaned_data.get('employment_type') == 'LOCAL':
            if cleaned_data.get('pf_applicable') is True:
                raise forms.ValidationError({
                    'pf_applicable': 'Local employees cannot have PF deduction enabled.'
                })
            if cleaned_data.get('esic_applicable') is True:
                raise forms.ValidationError({
                    'esic_applicable': 'Local employees cannot have ESIC deduction enabled.'
                })
        return cleaned_data

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin listing/options for role master data."""
    list_display = ('name', 'overtime_rate_per_hour', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    """Admin create/edit behavior for employee and linked auth user records."""
    form = EmployeeAdminForm
    exclude = ('user',)
    list_display = (
        'name',
        'role',
        'phone_number',
        'employment_type',
        'pf_applicable',
        'esic_applicable',
        'get_system_id',
        'is_active',
    )
    search_fields = ('name', 'phone_number', 'user__username')
    list_filter = ('is_active', 'role')
    fieldsets = (
        ('Personal Details', {
            'fields': (
                'name',
                'phone_number',
                'father_name',
                'email',
                'join_date',
                'is_active',
            )
        }),
        ('Employment Classification & Statutory Settings', {
            'fields': (
                'employment_type',
                'pf_applicable',
                'esic_applicable',
                'pf_rate',
                'esic_rate',
            )
        }),
        ('Work & Financial Details', {
            'fields': (
                'role',
                'daily_wage',
                'working_location',
                'current_address',
                'permanent_address',
                'aadhar_number',
                'pan_number',
                'uan_number',
                'esic_number',
                'bank_account_no',
            )
        }),
    )

    class Media:
        """Attach dynamic admin JS for classification-dependent form behavior."""
        js = ('admin/js/employee_classification.js',)

    def get_system_id(self, obj):
        """Expose linked auth username in employee list display."""
        return obj.user.username if obj.user else "-"
    get_system_id.short_description = 'System ID'

    def save_model(self, request, obj, form, change):
        """Create/update employee and keep linked auth user state consistent."""
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
