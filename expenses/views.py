"""Expense view handlers.

Module: expenses.views
App: expenses
Purpose: Expense entry/edit/delete workflows plus CSV/PDF exports and dashboard
totals.
Key responsibilities: Daily expense capture, 7-day edit lock enforcement,
summary aggregations, and export generation.
Dependencies: expenses.models.Expense, xhtml2pdf, manager_required decorator.
Author note: 7-day lock policy protects accounting closure from backdated
tampering.
"""

# ============================================================
# IMPORTS
# ============================================================
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.views.decorators.http import require_POST
from xhtml2pdf import pisa

from portal.decorators import manager_required

from .models import Expense

EDIT_LOCK_DAYS = 7


def get_lock_date():
    """Return cutoff date older than which expense rows become immutable.

    Returns:
        date: Cutoff date for edits/deletes.

    Business Rule:
        Expenses older than the lock window are immutable.
    """
    return date.today() - timedelta(days=EDIT_LOCK_DAYS)


# ============================================================
# DASHBOARD
# ============================================================
@manager_required
def expense_dashboard(request, viewing_as_owner=False):
    """Render expense dashboard and handle add-expense submissions.

    Args:
        request (HttpRequest): Incoming request.
        viewing_as_owner (bool): Owner view flag (unused here).

    Returns:
        HttpResponse: Expense dashboard page.

    Raises:
        None.

    Business Rule:
        Dashboard aggregates follow calendar boundaries for reporting.
    """
    if request.method == "POST":
        expense_date_str = request.POST.get("date")
        category = request.POST.get("category")
        description = request.POST.get("description")
        amount = request.POST.get("amount")
        payment_mode = request.POST.get("payment_mode")

        if not all([expense_date_str, category, description, amount, payment_mode]):
            messages.error(request, "All fields are required.")
            return redirect("expenses:expense_dashboard")

        try:
            # Reason: Decimal avoids float drift for currency amounts.
            expense_amount = Decimal(amount).quantize(Decimal('0.01'))
        except (ValueError, TypeError):
            messages.error(request, "Invalid amount. Please enter a valid number.")
            return redirect("expenses:expense_dashboard")
        
        Expense.objects.create(
            date=expense_date_str,
            category=category,
            description=description,
            amount=expense_amount,
            payment_mode=payment_mode,
            created_by=request.user,
        )

        messages.success(request, "Expense added successfully.")
        return redirect("expenses:expense_dashboard")

    selected_date = request.GET.get("date")
    
    try:
        base_date = (
            date.fromisoformat(selected_date)
            if selected_date
            else date.today()
        )
    except ValueError:
        base_date = date.today()

    # Reason: Grouped totals drive per-category dashboard charts.
    category_totals = (
        Expense.objects
        .filter(date=base_date)
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("category")
    )

    # BUSINESS RULE: Monthly totals are computed on calendar-month boundaries.
    # month boundaries
    month_start = base_date.replace(day=1)

    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    # Monday = 0, Sunday = 6
    week_start = base_date - timedelta(days=base_date.weekday())
    week_end = week_start + timedelta(days=6)

    # Reason: Weekly grouping supports short-term spend visibility.
    weekly_category_totals = (
        Expense.objects
        .filter(date__range=[week_start, week_end])
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("category")
    )

    # Reason: Show most recent entries first for daily review.
    expenses = Expense.objects.filter(date=base_date).order_by("-created_at")

    daily_total = expenses.aggregate(
        total=Sum("amount")
    )["total"] or 0

    weekly_total = Expense.objects.filter(
        date__range=[week_start, week_end]
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0

    monthly_total = (
        Expense.objects
        .filter(date__gte=month_start, date__lt=month_end)
        .aggregate(total=Sum("amount"))
    )["total"] or 0

    monthly_category_totals = (
        Expense.objects
        .filter(date__gte=month_start, date__lt=month_end)
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("category")
    )

    return render(request, "expenses/expense_dashboard.html", {
        "expenses": expenses,
        "total_amount": daily_total,
        "weekly_total": weekly_total,
        "category_totals": category_totals,
        "weekly_category_totals": weekly_category_totals,
        "monthly_total": monthly_total,
        "monthly_category_totals": monthly_category_totals,
        "lock_date": get_lock_date(),
    })

@manager_required
@require_POST
def delete_expense(request, expense_id):
    """Delete an expense entry when it is inside the lock window.

    Args:
        request (HttpRequest): Incoming request.
        expense_id (int): Expense id.

    Returns:
        HttpResponse: Redirect to expense dashboard.

    Raises:
        Http404: When the expense does not exist.

    Business Rule:
        Expenses older than the lock window cannot be deleted.
    """
    expense = get_object_or_404(Expense, id=expense_id)
    lock_date = get_lock_date()

    # BUSINESS RULE: 7-day lock prevents destructive edits after accounting review cycle.
    if expense.date < lock_date:
        messages.error(
            request,
            "This expense is locked and cannot be deleted.",
        )
    else:
        expense.delete()
        messages.success(request, "Expense deleted Successfully.")
    return redirect("expenses:expense_dashboard")

@manager_required
def edit_expense(request, expense_id):
    """Edit an expense record if still inside the lock window.

    Args:
        request (HttpRequest): Incoming request.
        expense_id (int): Expense id.

    Returns:
        HttpResponse: Edit form or redirect to dashboard.

    Raises:
        Http404: When the expense does not exist.

    Business Rule:
        Edits are blocked for expenses older than the lock window.
    """
    expense = get_object_or_404(Expense, id=expense_id)

    if request.method == "POST":
        new_date = request.POST.get("date")
        new_amount = request.POST.get("amount")
        
        # Reason: Reject invalid dates to keep reporting windows consistent.
        if new_date:
            try:
                expense.date = date.fromisoformat(new_date)
            except ValueError:
                messages.error(request, "Invalid date format.")
                return redirect("expenses:expense_dashboard")
        
        # Reason: Reject invalid amounts to protect financial integrity.
        if new_amount:
            try:
                # Reason: Decimal avoids float drift for currency amounts.
                expense.amount = Decimal(new_amount).quantize(Decimal('0.01'))
            except (ValueError, TypeError):
                messages.error(
                    request,
                    "Invalid amount. Please enter a valid number.",
                )
                return redirect("expenses:expense_dashboard")
        
        expense.category = request.POST.get("category")
        expense.description = request.POST.get("description")
        expense.payment_mode = request.POST.get("payment_mode")
        expense.save()

        messages.success(request, "Expense updated.")
        return redirect("expenses:expense_dashboard")
    
    lock_date = get_lock_date()

    if expense.date < lock_date:
        messages.error(
            request,
            "This expense is locked and cannot be edited.",
        )
        return redirect("expenses:expense_dashboard")

    return render(request, "expenses/edit_expense.html", {
        "expense": expense
    })


# ============================================================
# EXPORTS
# ============================================================
@manager_required
def export_expenses_csv(request, viewing_as_owner=False):
    """Export one-day expense slice as CSV.

    Args:
        request (HttpRequest): Incoming request.
        viewing_as_owner (bool): Owner view flag (unused here).

    Returns:
        HttpResponse: CSV response with daily expenses.

    Raises:
        ValueError: When date is invalid.

    Business Rule:
        Export is date-scoped to avoid large downloads in production.
    """
    selected_date = request.GET.get("date")
    export_date = (
        date.fromisoformat(selected_date)
        if selected_date
        else date.today()
    )

    expenses = Expense.objects.filter(date=export_date)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="expenses_{export_date}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow([
        "Date",
        "Category",
        "Description",
        "Amount",
        "Payment Mode",
    ])

    for exp in expenses:
        writer.writerow([
            exp.date,
            exp.get_category_display(),
            exp.description,
            exp.amount,
            exp.get_payment_mode_display(),
        ])

    return response

@manager_required
def daily_expense_pdf(request):
    """Export one-day grouped expense summary as PDF.

    Args:
        request (HttpRequest): Incoming request.

    Returns:
        HttpResponse: PDF response containing daily expense summary.

    Raises:
        ValueError: When date is invalid.

    Business Rule:
        Grouped totals use category and payment_mode for audit clarity.
    """
    selected_date = request.GET.get("date")
    report_date = (
        date.fromisoformat(selected_date)
        if selected_date
        else date.today()
    )

    expenses = Expense.objects.filter(date=report_date)

    # Reason: Grouped output matches PDF summary layout expectations.
    grouped_raw = (
        expenses
        .values('category', 'payment_mode')
        .annotate(
            entry_count=Count('id'),
            total_amount=Sum('amount')
        )
        .order_by('category', 'payment_mode')
    )

    # Reason: Display labels are required for human-readable reports.
    grouped_expenses = []
    for item in grouped_raw:
        dummy = Expense(
            category=item['category'],
            payment_mode=item['payment_mode']
        )
        grouped_expenses.append({
            'category':     dummy.get_category_display(),
            'payment_mode': dummy.get_payment_mode_display(),
            'entry_count':  item['entry_count'],
            'total_amount': item['total_amount'],
        })

    total_amount = expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_entries = expenses.count()

    template = get_template("expenses/daily_expense_pdf.html")
    html = template.render({
        'report_date':      report_date,
        'generated_at':     datetime.now().strftime('%d %b %Y, %I:%M %p'),
        'grouped_expenses': grouped_expenses,
        'total_amount':     total_amount,
        'total_entries':    total_entries,
    })

    result = io.BytesIO()
    pisa.CreatePDF(html, dest=result)

    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="daily_expenses_{report_date}.pdf"'
    )
    return response

