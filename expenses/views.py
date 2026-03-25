from django.shortcuts import render, redirect
from decimal import Decimal
from django.contrib import messages
from urllib3 import request
from .models import Expense
from portal.decorators import manager_required
from datetime import date, timedelta
from django.db.models import Sum
import csv
from django.http import HttpResponse
from datetime import date
from django.template.loader import get_template
from xhtml2pdf import pisa
import io

EDIT_LOCK_DAYS = 7


from datetime import date, timedelta

lock_date = date.today() - timedelta(days=EDIT_LOCK_DAYS)

@manager_required
def expense_dashboard(request):
    if request.method == "POST":
        date = request.POST.get("date")
        category = request.POST.get("category")
        description = request.POST.get("description")
        amount = request.POST.get("amount")
        payment_mode = request.POST.get("payment_mode")

        if not all([date, category, description, amount, payment_mode]):
            messages.error(request, "All fields are required.")
            return redirect("expenses:expense_dashboard")

        Expense.objects.create(
            date=date,
            category=category,
            description=description,
            amount=Decimal(amount),
            payment_mode=payment_mode,
            created_by=request.user,
        )

        messages.success(request, "Expense added successfully.")
        return redirect("expenses:expense_dashboard")

    from datetime import date
    
    selected_date = request.GET.get("date")

    base_date = (
        date.fromisoformat(selected_date)
        if selected_date
        else date.today()
    )

    category_totals = (
        Expense.objects
        .filter(date=base_date)
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("category")
    )

    #month boundaries
    month_start = base_date.replace(day=1)

    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    # Monday = 0, Sunday = 6
    week_start = base_date - timedelta(days=base_date.weekday())
    week_end = week_start + timedelta(days=6)

    weekly_category_totals = (
    Expense.objects
    .filter(date__range=[week_start, week_end])
    .values("category")
    .annotate(total=Sum("amount"))
    .order_by("category")
    )

    expenses = Expense.objects.filter(
        date=base_date
    ).order_by("-created_at")

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
        "lock_date": lock_date,
    })

@manager_required
def delete_expense(request, expense_id):
    expense = Expense.objects.get(id=expense_id)
    lock_date = date.today() - timedelta(days=EDIT_LOCK_DAYS)

    if expense.date < lock_date:
        messages.error(
            request,
            "This expense is locked and cannot be deleted."
        )
    return redirect("expenses:expense_dashboard")
    expense.delete()
    messages.success(request, "Expense deleted Successfully.")
    return redirect("expenses:expense_dashboard")

from datetime import timedelta

@manager_required
def edit_expense(request, expense_id):
    expense = Expense.objects.get(id=expense_id)

    if request.method == "POST":
        expense.date = request.POST.get("date")
        expense.category = request.POST.get("category")
        expense.description = request.POST.get("description")
        expense.amount = request.POST.get("amount")
        expense.payment_mode = request.POST.get("payment_mode")
        expense.save()

        messages.success(request, "Expense updated.")
        return redirect("expenses:expense_dashboard")
    
    lock_date = date.today() - timedelta(days=EDIT_LOCK_DAYS)

    if expense.date < lock_date:
        messages.error(
            request,
            "This expense is locked and cannot be edited."
        )
        return redirect("expenses:expense_dashboard")

        return render(request, "expenses/edit_expense.html", {
            "expense": expense
        })

@manager_required
def export_expenses_csv(request):
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
    from datetime import datetime
    from django.db.models import Count

    selected_date = request.GET.get("date")
    report_date = (
        date.fromisoformat(selected_date)
        if selected_date
        else date.today()
    )

    expenses = Expense.objects.filter(date=report_date)

    # Group by category + payment_mode with count and sum
    grouped_raw = (
        expenses
        .values('category', 'payment_mode')
        .annotate(
            entry_count=Count('id'),
            total_amount=Sum('amount')
        )
        .order_by('category', 'payment_mode')
    )

    # Convert to display names using model methods
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

    total_amount  = expenses.aggregate(total=Sum('amount'))['total'] or 0
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
