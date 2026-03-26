from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from django.db.models.functions import Coalesce
from decimal import Decimal

from portal.decorators import manager_required
from .models import Bill


@manager_required
def billing_dashboard(request, viewing_as_owner=False):

    # ==========================
    # HANDLE BILL UPLOAD (POST)
    # ==========================
    if request.method == "POST":
        description = request.POST.get("description")
        amount = request.POST.get("amount")
        pdf_file = request.FILES.get("pdf_file")

        if not description or not amount or not pdf_file:
            messages.error(request, "All fields are required.")
            return redirect("billing:billing_dashboard")

        try:
            bill_amount = Decimal(amount).quantize(Decimal('0.01'))
        except (ValueError, TypeError):
            messages.error(request, "Invalid amount. Please enter a valid number.")
            return redirect("billing:billing_dashboard")
        
        Bill.objects.create(
            description=description,
            amount=bill_amount,
            pdf_file=pdf_file,
            is_paid=False
        )

        messages.success(request, "Bill uploaded successfully.")
        return redirect("billing:billing_dashboard")  # 🔒 PRG pattern

    # ==========================
    # GET: DASHBOARD DATA
    # ==========================
    bills = Bill.objects.all().order_by("-created_at")

    total_bills = bills.count()

    total_paid = bills.filter(is_paid=True).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    total_unpaid = bills.filter(is_paid=False).aggregate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )["total"]

    unpaid_count = bills.filter(is_paid=False).count()

    # percentages (safe)
    total_amount = total_paid + total_unpaid
    paid_percentage = int((total_paid / total_amount) * 100) if total_amount else 0
    unpaid_percentage = 100 - paid_percentage
    unpaid_bill_percentage = int((unpaid_count / total_bills) * 100) if total_bills else 0

    context = {
        "bills": bills,
        "total_bills": total_bills,
        "total_paid": total_paid,
        "total_unpaid": total_unpaid,
        "unpaid_count": unpaid_count,
        "paid_percentage": paid_percentage,
        "unpaid_percentage": unpaid_percentage,
        "unpaid_bill_percentage": unpaid_bill_percentage,
    }

    return render(request, "billing/billing_dashboard.html", context)

from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST

@require_POST
def toggle_bill_status(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    bill.is_paid = not bill.is_paid
    bill.save()

    if bill.is_paid:
        messages.success(request, "Bill marked as PAID.")
    else:
        messages.warning(request, "Bill marked as UNPAID.")

    return redirect("billing:billing_dashboard")


@require_POST
def delete_bill(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    bill.delete()
    messages.success(request, "Bill deleted successfully.")
    return redirect("billing:billing_dashboard")