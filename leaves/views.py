from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

# Importing your specific access control
from portal.decorators import manager_required 

from .forms import AssignLeaveForm
from .models import LeaveRecord
from .services import assign_leave

@manager_required
def assign_leave_view(request):
    """View to handle the form submission and call the service layer."""
    if request.method == 'POST':
        form = AssignLeaveForm(request.POST)
        if form.is_valid():
            try:
                # The service layer handles all logic, DB writes, and quotas
                leave = assign_leave(
                    employee=form.cleaned_data['employee'],
                    leave_type=form.cleaned_data['leave_type'],
                    from_date=form.cleaned_data['from_date'],
                    to_date=form.cleaned_data['to_date'],
                    total_days=form.cleaned_data['total_days'],
                    reason=form.cleaned_data['reason'],
                    address_on_leave=form.cleaned_data['address_on_leave'],
                    application_date=timezone.now().date(),
                    approved_by=request.user,
                    department=form.cleaned_data['department']
                )
                messages.success(request, f"Leave {leave.sl_number} assigned successfully!")
                return redirect('leave_list')
            except ValidationError as e:
                # Catch service-layer errors (like insufficient quota) and show to manager
                messages.error(request, str(e.message))
    else:
        form = AssignLeaveForm()

    return render(request, 'leaves/assign_leave.html', {'form': form})

@manager_required
def leave_list_view(request):
    """Shows all leaves for the single-tenant contractor."""
    leaves = LeaveRecord.objects.all().select_related('employee', 'approved_by', 'allocation')
    return render(request, 'leaves/leave_list.html', {'leaves': leaves})

@manager_required
def generate_leave_pdf_view(request, leave_id):
    """Generates the hardcopy-style PDF using xhtml2pdf."""
    leave = get_object_or_404(LeaveRecord, id=leave_id)
    template = get_template('leaves/leave_pdf.html')
    
    context = {
        'leave': leave,
        'employee': leave.employee,
        'allocation': leave.allocation,
    }
    
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    # Set filename to the SL Number
    response['Content-Disposition'] = f'attachment; filename="Sanction_Letter_{leave.sl_number}.pdf"'
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('Error generating PDF', status=500)
    
    return response