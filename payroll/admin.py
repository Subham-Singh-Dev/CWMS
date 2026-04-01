from django.contrib import admin
from django.utils.html import format_html  # <--- NEW IMPORT
from django.urls import reverse            # <--- NEW IMPORT
from .models import MonthlySalary, Advance

@admin.register(Advance)
class AdvanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'amount', 'remaining_amount', 'issued_date', 'settled')
    list_filter = ('settled', 'issued_date')
    search_fields = ('employee__name',)
    ordering = ('issued_date',)
    
    # Pro Tip: If you have 1000 employees, a dropdown is slow. 
    # This makes it a searchable box (Requires search_fields on EmployeeAdmin).
    # autocomplete_fields = ['employee'] 

@admin.register(MonthlySalary)
class MonthlySalaryAdmin(admin.ModelAdmin):
    # 1. ADDED 'download_payslip_button' to the list
    list_display = (
        'employee', 
        'month', 
        'gross_pay', 
        'advance_deducted', 
        'net_pay', 
        'is_paid',
        'download_payslip_button' 
    )
    list_filter = ('month', 'is_paid')
    search_fields = ('employee__name',)

    # 🔒 IMPORTANT: Make payroll immutable in admin
    readonly_fields = (
        'employee',
        'month',
        'days_present',
        'half_days',
        'paid_leaves',
        'overtime_hours',
        'gross_pay',
        'advance_deducted',
        'pf_deduction',
        'esic_deduction',
        'pf_rate_snapshot',
        'esic_rate_snapshot',
        'total_deductions',
        'net_pay',
        'remaining_advance',
        'is_paid',
        'paid_on',
        'generated_at',
    )
    fieldsets = (
        ('Employee & Period', {
            'fields': ('employee', 'month', 'generated_at')
        }),
        ('Attendance Snapshot', {
            'fields': ('days_present', 'half_days', 'paid_leaves', 'overtime_hours')
        }),
        ('Financial Snapshot', {
            'fields': (
                'gross_pay',
                'advance_deducted',
                'pf_deduction',
                'esic_deduction',
                'total_deductions',
                'net_pay',
                'remaining_advance',
            )
        }),
        ('Statutory Rate Snapshots', {
            'fields': ('pf_rate_snapshot', 'esic_rate_snapshot')
        }),
        ('Payment Status', {
            'fields': ('is_paid', 'paid_on')
        }),
    )

    # 1. Prevent Manual Creation (Always True for Integrity)
    def has_add_permission(self, request):
        return False

    # 2. Prevent Deletion (COMMENTED OUT FOR TESTING)
    # Uncomment this block below when you are finished with the project.
    # def has_delete_permission(self, request, obj=None):
    #    return False

    # --- NEW FUNCTION: Creates the Button ---
    def download_payslip_button(self, obj):
        # This generates the URL: /payroll/payslip/123/
        url = reverse('download_payslip', args=[obj.id])
        
        # This renders a nice blue button
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background-color: #417690; color: white; padding: 5px 10px; border-radius: 4px; font-weight: bold;">Download PDF</a>', 
            url
        )
    
    download_payslip_button.short_description = 'Payslip'