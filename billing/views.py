"""Billing view handlers.

Module: billing.views
App: billing
Purpose: Manager-facing bill upload/listing and payment state transitions.
Key responsibilities: PRG-safe uploads, bill status updates, partial payment
tracking, and PDF exports for summaries.
Dependencies: billing.models.Bill, manager_required decorator, xhtml2pdf.
Author note: Uses PRG (Post-Redirect-Get) to avoid duplicate uploads on refresh.
"""

# ============================================================
# IMPORTS
# ============================================================
from datetime import datetime
from decimal import Decimal
import decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from xhtml2pdf import pisa

from portal.decorators import manager_required

from .models import Bill

from billing.models import Bill, BillingAccount
from datetime import datetime as dt


@manager_required
def billing_dashboard(request, viewing_as_owner=False):
    """Render bill dashboard and handle upload form submissions.

    Args:
        request (HttpRequest): Incoming request.
        viewing_as_owner (bool): Flag for owner-only views (unused here).

    Returns:
        HttpResponse: Billing dashboard page.

    Raises:
        None.

    Business Rule:
        Bill uploads must use PRG flow to prevent duplicate POSTs on refresh.
    """
    selected_type = request.GET.get("type", Bill.BILL_TYPE_DEBTOR).strip().lower()
    if selected_type not in {Bill.BILL_TYPE_CLIENT, Bill.BILL_TYPE_DEBTOR}:
        selected_type = Bill.BILL_TYPE_DEBTOR

    selected_month_str = request.GET.get("month", timezone.now().strftime("%Y-%m")).strip()
    try:
        selected_month = datetime.strptime(selected_month_str, "%Y-%m")
    except ValueError:
        selected_month = timezone.now()
        selected_month_str = selected_month.strftime("%Y-%m")

    # ============================================================
    # HANDLE BILL UPLOAD (POST)
    # ============================================================
    if request.method == "POST":
        description = request.POST.get("description")
        amount = request.POST.get("amount")
        pdf_file = request.FILES.get("pdf_file")
        bill_type = request.POST.get("bill_type", Bill.BILL_TYPE_DEBTOR).strip().lower()
        if bill_type not in {Bill.BILL_TYPE_CLIENT, Bill.BILL_TYPE_DEBTOR}:
            bill_type = Bill.BILL_TYPE_DEBTOR
        redirect_url = f"{request.path}?type={selected_type}&month={selected_month_str}"

        if not description or not amount or not pdf_file:
            messages.error(request, "All fields are required.")
            return redirect(redirect_url)

        try:
            # Reason: Decimal avoids float drift in financial values.
            bill_amount = Decimal(amount).quantize(Decimal('0.01'))
        except (ValueError, TypeError):
            messages.error(request, "Invalid amount. Please enter a valid number.")
            return redirect(redirect_url)
        
        account_id = request.POST.get('account_id') or None
        account = None
        if account_id:
            try:
                account = BillingAccount.objects.get(id=account_id)
            except BillingAccount.DoesNotExist:
                pass
        
        Bill.objects.create(
            bill_type=bill_type,
            description=description,
            amount=bill_amount,
            pdf_file=pdf_file,
            is_paid=False,
            account=account
        )

        messages.success(request, "Bill uploaded successfully.")
        return redirect(redirect_url)  # 🔒 PRG pattern

    # ============================================================
    # GET: DASHBOARD DATA
    # ============================================================
    # Reason: Filter by type for accurate debtor/client views.
    bills = Bill.objects.filter(bill_type=selected_type).order_by("-created_at")
    # Reason: Month filter drives KPI totals and charts.
    filtered_bills = bills.filter(
        created_at__year=selected_month.year,
        created_at__month=selected_month.month,
    )

    total_bills = filtered_bills.count()

    # Reason: Use GST-included totals for accurate outstanding balance.
    taxable_amount = filtered_bills.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    gst_rate = Decimal("0.18")
    gst_amount = (taxable_amount * gst_rate).quantize(Decimal("0.01"))
    total_amount_with_gst = taxable_amount + gst_amount

    total_paid = filtered_bills.aggregate(
        total=Coalesce(Sum("paid_amount"), Decimal("0.00"))
    )["total"]

    total_unpaid = total_amount_with_gst - total_paid
    unpaid_count = filtered_bills.filter(is_paid=False).count()

    # Monthly summary cards
    today = timezone.now().date()
    monthly_bills = filtered_bills
    monthly_bill_count = monthly_bills.count()

    gst_rate = Decimal("0.18")
    gst_amount = (taxable_amount * gst_rate).quantize(Decimal("0.01"))
    total_amount_with_gst = (taxable_amount + gst_amount).quantize(Decimal("0.01"))

    # Reason: Guard against division by zero in percentage calculations.
    total_amount = total_paid + total_unpaid
    paid_percentage = int((total_paid / total_amount) * 100) if total_amount else 0
    unpaid_percentage = 100 - paid_percentage
    unpaid_bill_percentage = int((unpaid_count / total_bills) * 100) if total_bills else 0

    all_accounts = BillingAccount.objects.all().order_by('name')

    debtor_health = ""
    debtor_health_color = ""
    if selected_type == Bill.BILL_TYPE_DEBTOR:
        if total_unpaid <= Decimal("50000"):
            debtor_health = "Healthy"
            debtor_health_color = "green"
        elif total_unpaid < Decimal("200000"):
            debtor_health = "Watch"
            debtor_health_color = "orange"
        else:
            debtor_health = "Critical"
            debtor_health_color = "red"

    context = {
        "bills": filtered_bills,
        "total_bills": total_bills,
        "total_paid": total_paid,
        "total_unpaid": total_unpaid,
        "unpaid_count": unpaid_count,
        "paid_percentage": paid_percentage,
        "unpaid_percentage": unpaid_percentage,
        "unpaid_bill_percentage": unpaid_bill_percentage,
        "monthly_bill_count": monthly_bill_count,
        "taxable_amount": taxable_amount,
        "gst_amount": gst_amount,
        "total_amount_with_gst": total_amount_with_gst,
        "today_date": today.isoformat(),
        "selected_type": selected_type,
        "selected_month": selected_month_str,
        "selected_month_display": selected_month.strftime("%B %Y"),
        "debtor_health": debtor_health,
        "debtor_health_color": debtor_health_color,
        "all_accounts": all_accounts,
    }

    return render(request, "billing/billing_dashboard.html", context)

@manager_required
@require_POST
def toggle_bill_status(request, bill_id):
    """Toggle paid/unpaid state for a bill.

    Args:
        request (HttpRequest): Incoming request.
        bill_id (int): Bill id.

    Returns:
        HttpResponse: Redirect to billing dashboard.

    Raises:
        Http404: When the bill does not exist.

    Business Rule:
        Paid bills use the GST-inclusive total as the paid amount.
    """
    bill = get_object_or_404(Bill, id=bill_id)
    selected_type = request.POST.get("type", bill.bill_type)
    selected_month = request.POST.get("month", timezone.now().strftime("%Y-%m"))

    if bill.is_paid:
        bill.paid_amount = Decimal("0.00")
        bill.paid_on = None
    else:
        paid_on_input = request.POST.get("paid_on")
        bill.paid_amount = bill.total_with_gst
        if paid_on_input:
            paid_on_date = parse_date(paid_on_input)
            if paid_on_date:
                bill.paid_on = paid_on_date

    bill.save()

    return redirect(
        f"{reverse('billing:billing_dashboard')}?type={selected_type}&month={selected_month}"
    )


@manager_required
@require_POST
@transaction.atomic()
def record_payment(request, bill_id):
    """Record a partial or full payment against a bill.

    Args:
        request (HttpRequest): Incoming request.
        bill_id (int): Bill id.

    Returns:
        HttpResponse: Redirect to billing dashboard.

    Raises:
        Http404: When the bill does not exist.

    Business Rule:
        Payment updates are atomic to avoid partial writes under concurrency.
    """
    bill = get_object_or_404(Bill, id=bill_id)
    
    # Fetch parameters for redirect
    selected_type = request.POST.get('type', 'client')
    selected_month = request.POST.get('month', '')
    
    try:
        payment_amount = Decimal(request.POST.get('amount', 0))
        payment_mode = request.POST.get('payment_mode', '')

        bill.paid_amount = (bill.paid_amount or Decimal('0')) + payment_amount
        bill.payment_mode = payment_mode

        if bill.paid_amount >= bill.total_amount:
            bill.status = 'paid'

        bill.save()
        messages.success(
            request,
            f"Payment of ₹{payment_amount} recorded successfully for "
            f"BILL-{bill.id:04d}."
        )
            
    except (ValueError, TypeError, decimal.InvalidOperation):
        messages.error(request, "Invalid payment amount entered.")

    return redirect(f"{reverse('billing:billing_dashboard')}?type={selected_type}&month={selected_month}")


@manager_required
@require_POST
def delete_bill(request, bill_id):
    """Hard-delete a bill row from dashboard action.

    Args:
        request (HttpRequest): Incoming request.
        bill_id (int): Bill id.

    Returns:
        HttpResponse: Redirect to billing dashboard.

    Raises:
        Http404: When the bill does not exist.

    Business Rule:
        Deletes are POST-only to prevent accidental data loss.
    """
    selected_type = request.POST.get("type", Bill.BILL_TYPE_DEBTOR)
    selected_month = request.POST.get("month", timezone.now().strftime("%Y-%m"))
    bill = get_object_or_404(Bill, id=bill_id)
    bill.delete()
    messages.success(request, "Bill deleted successfully.")
    return redirect(
        f"{reverse('billing:billing_dashboard')}?type={selected_type}&month={selected_month}"
    )

def billing_pdf(request):
    """Export billing summary as PDF for a selected month/year.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: PDF response containing billing summary.

    Raises:
        None.

    Business Rule:
        Uses created_at timestamps to match bill lifecycle records.
    """
    # Reason: Normalize missing month/year to current period.
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    if not month:
        month = datetime.today().month
    if not year:
        year = datetime.today().year
        
    # Reason: created_at is the authoritative timestamp for bill lifecycle.
    bills = Bill.objects.filter(
        created_at__month=month,
        created_at__year=year,
    ).order_by('created_at')
    
    # Calculate totals by type
    total_credit = sum(b.amount for b in bills if b.bill_type == 'Credit')
    total_debtor = sum(b.amount for b in bills if b.bill_type == 'Debtor')
    grand_total = total_credit + total_debtor
    
    context = {
        'bills': bills,
        'month_name': datetime(int(year), int(month), 1).strftime('%B %Y'),
        'total_credit': total_credit,
        'total_debtor': total_debtor,
        'grand_total': grand_total,
        'BRAND_SHORT_NAME': 'CWMS'
    }
    
    template = get_template('billing/billing_pdf.html')
    html = template.render(context)
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="Billing_Summary_{month}_{year}.pdf"'
    )
    
    # Generate PDF
    pisa_status = pisa.CreatePDF(html, dest=response)
    
    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response

@manager_required
def account_list(request):
    """List billing accounts (vendor/client masters)."""
    accounts = BillingAccount.objects.filter(
        created_by=request.user
    ).prefetch_related('bills').order_by('name')
    
    # Make all accounts visible to all managers (not just creator)
    # since bills are shared — override above with:
    accounts = BillingAccount.objects.all().order_by('name')
    
    return render(request, 'billing/account_list.html', {
        'accounts': accounts,
    })


@manager_required
@require_POST
def account_add(request):
    """Create a new billing account."""
    name = request.POST.get('name', '').strip()
    if not name:
        messages.error(request, 'Account name is required.')
        return redirect('billing:account_list')

    if BillingAccount.objects.filter(name__iexact=name).exists():
        messages.error(request, f'Account "{name}" already exists.')
        return redirect('billing:account_list')

    BillingAccount.objects.create(
        name=name,
        address=request.POST.get('address') or None,
        gst_number=request.POST.get('gst_number') or None,
        phone=request.POST.get('phone') or None,
        created_by=request.user,
    )
    messages.success(request, f'Account "{name}" created.')
    return redirect('billing:account_list')


@manager_required
@require_POST
def account_delete(request, account_id):
    """Delete a billing account (bills become unlinked)."""
    acc = get_object_or_404(BillingAccount, id=account_id)
    name = acc.name
    acc.delete()
    messages.success(request, f'Account "{name}" deleted. Bills are now unassigned.')
    return redirect('billing:account_list')


@manager_required
def account_statement_pdf(request, account_id):
    """Export all bills for an account split by Receivables (Dr) and Payables (Cr)."""
    account = get_object_or_404(BillingAccount, id=account_id)
    
    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')
    
    today = timezone.now().date()
    from_date = dt.strptime(from_date_str, '%Y-%m-%d').date() if from_date_str else today.replace(day=1, month=1)
    to_date = dt.strptime(to_date_str, '%Y-%m-%d').date() if to_date_str else today
    
    # Base ledger collection query
    bills = account.bills.filter(
        created_at__date__gte=from_date,
        created_at__date__lte=to_date,
    ).order_by('created_at')
    
    gst_rate = Decimal('0.18')

    # 1. RECEIVABLES (Client Side) Calculations
    client_bills = bills.filter(bill_type='client')
    rec_base = client_bills.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    rec_gst = (rec_base * gst_rate).quantize(Decimal('0.01'))
    total_receivable_with_gst = rec_base + rec_gst
    total_received = client_bills.aggregate(t=Sum('paid_amount'))['t'] or Decimal('0.00')
    outstanding_receivable = max(total_receivable_with_gst - total_received, Decimal('0.00'))

    # 2. PAYABLES (Debtor Side) Calculations
    debtor_bills = bills.filter(bill_type='debtor')
    pay_base = debtor_bills.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    pay_gst = (pay_base * gst_rate).quantize(Decimal('0.01'))
    total_payable_with_gst = pay_base + pay_gst
    total_paid = debtor_bills.aggregate(t=Sum('paid_amount'))['t'] or Decimal('0.00')
    outstanding_payable = max(total_payable_with_gst - total_paid, Decimal('0.00'))

    # 3. Overall Totals for Ledger Reference
    total_base = rec_base + pay_base
    total_gst = rec_gst + pay_gst
    total_with_gst = total_base + total_gst
    net_difference = outstanding_receivable - outstanding_payable

    context = {
        'account': account,
        'bills': bills,
        'from_date': from_date,
        'to_date': to_date,
        'today': today,
        
        # General Table Summary Totals
        'total_base': total_base,
        'total_gst': total_gst,
        'total_with_gst': total_with_gst,
        
        # Receivables (Dr) Matrix Breakdown
        'total_receivable_with_gst': total_receivable_with_gst,
        'total_received': total_received,
        'outstanding_receivable': outstanding_receivable,
        
        # Payables (Cr) Matrix Breakdown
        'total_payable_with_gst': total_payable_with_gst,
        'total_paid': total_paid,
        'outstanding_payable': outstanding_payable,
        'net_difference': net_difference,
        'is_receivable_dominant': outstanding_receivable >= outstanding_payable,
    }
    
    template = get_template('billing/account_statement_pdf.html')
    html = template.render(context)
    
    response = HttpResponse(content_type='application/pdf')
    slug = account.name.replace(' ', '_')
    response['Content-Disposition'] = (
        f'attachment; filename="Statement_{slug}_{from_date}_to_{to_date}.pdf"'
    )
    
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('PDF generation failed: <pre>' + html + '</pre>')
    return response
