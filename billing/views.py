"""
Module: billing.views
App: billing
Purpose: Manager-facing bill upload/listing and payment-state transitions.
Dependencies: billing.models.Bill, manager_required decorator.
Author note: Uses PRG (Post-Redirect-Get) to avoid duplicate uploads on refresh.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from django.db.models.functions import Coalesce
from decimal import Decimal
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import datetime
from django.urls import reverse

from portal.decorators import manager_required
from .models import Bill


@manager_required
def billing_dashboard(request, viewing_as_owner=False):
    """Render bill dashboard and handle upload form submissions."""
    selected_type = request.GET.get("type", Bill.BILL_TYPE_DEBTOR).strip().lower()
    if selected_type not in {Bill.BILL_TYPE_CLIENT, Bill.BILL_TYPE_DEBTOR}:
        selected_type = Bill.BILL_TYPE_DEBTOR

    selected_month_str = request.GET.get("month", timezone.now().strftime("%Y-%m")).strip()
    try:
        selected_month = datetime.strptime(selected_month_str, "%Y-%m")
    except ValueError:
        selected_month = timezone.now()
        selected_month_str = selected_month.strftime("%Y-%m")

    # ==========================
    # HANDLE BILL UPLOAD (POST)
    # ==========================
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
            bill_amount = Decimal(amount).quantize(Decimal('0.01'))
        except (ValueError, TypeError):
            messages.error(request, "Invalid amount. Please enter a valid number.")
            return redirect(redirect_url)
        
        Bill.objects.create(
            bill_type=bill_type,
            description=description,
            amount=bill_amount,
            pdf_file=pdf_file,
            is_paid=False
        )

        messages.success(request, "Bill uploaded successfully.")
        return redirect(redirect_url)  # 🔒 PRG pattern

    # ==========================
    # GET: DASHBOARD DATA
    # ==========================
    bills = Bill.objects.filter(bill_type=selected_type).order_by("-created_at")
    filtered_bills = bills.filter(
        created_at__year=selected_month.year,
        created_at__month=selected_month.month,
    )

    total_bills = filtered_bills.count()

    total_paid = filtered_bills.filter(is_paid=True).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    total_unpaid = filtered_bills.filter(is_paid=False).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    unpaid_count = filtered_bills.filter(is_paid=False).count()

    # Monthly summary cards (default: current month)
    today = timezone.now().date()
    monthly_bills = filtered_bills
    monthly_bill_count = monthly_bills.count()
    taxable_amount = monthly_bills.aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    gst_rate = Decimal("0.18")
    gst_amount = (taxable_amount * gst_rate).quantize(Decimal("0.01"))
    total_amount_with_gst = (taxable_amount + gst_amount).quantize(Decimal("0.01"))

    # percentages (safe)
    total_amount = total_paid + total_unpaid
    paid_percentage = int((total_paid / total_amount) * 100) if total_amount else 0
    unpaid_percentage = 100 - paid_percentage
    unpaid_bill_percentage = int((unpaid_count / total_bills) * 100) if total_bills else 0

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
    }

    return render(request, "billing/billing_dashboard.html", context)

@manager_required
@require_POST
def toggle_bill_status(request, bill_id):
    """Flip bill paid/unpaid state.

    SECURITY: POST-only to prevent status changes via crawlers/bookmarks.
    """
    bill = get_object_or_404(Bill, id=bill_id)
    selected_type = request.POST.get("type", bill.bill_type)
    selected_month = request.POST.get("month", timezone.now().strftime("%Y-%m"))

    if bill.is_paid:
        bill.is_paid = False
        bill.paid_on = None
        bill.save(update_fields=["is_paid", "paid_on"])
    else:
        selected_date_raw = request.POST.get("paid_on", "").strip()
        selected_date = parse_date(selected_date_raw) if selected_date_raw else None
        bill.is_paid = True
        bill.paid_on = selected_date or timezone.localdate()
        bill.save(update_fields=["is_paid", "paid_on"])

    if bill.is_paid:
        messages.success(request, "Bill marked as PAID.")
    else:
        messages.warning(request, "Bill marked as UNPAID.")

    return redirect(f"{reverse('billing:billing_dashboard')}?type={selected_type}&month={selected_month}")


@manager_required
@require_POST
def delete_bill(request, bill_id):
    """Hard-delete a bill row from dashboard action."""
    selected_type = request.POST.get("type", Bill.BILL_TYPE_DEBTOR)
    selected_month = request.POST.get("month", timezone.now().strftime("%Y-%m"))
    bill = get_object_or_404(Bill, id=bill_id)
    bill.delete()
    messages.success(request, "Bill deleted successfully.")
    return redirect(f"{reverse('billing:billing_dashboard')}?type={selected_type}&month={selected_month}")