from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("manager/billing/", views.billing_dashboard,name="billing_dashboard"),

    path("toggle_bill_status/<int:bill_id>/", views.toggle_bill_status, name="toggle_bill_status"),

    path("record-payment/<int:bill_id>/", views.record_payment, name="record_payment"),
    
    path('delete_bill/<int:bill_id>/', views.delete_bill, name='delete_bill'),
   
    path('manager/billing/pdf/', views.billing_pdf, name='billing_pdf'),

    path('accounts/', views.account_list, name='account_list'),

    path('accounts/add/', views.account_add, name='account_add'),

    path('accounts/<int:account_id>/delete/', views.account_delete, name='account_delete'),
    
    path('accounts/<int:account_id>/statement/pdf/', views.account_statement_pdf, name='account_statement_pdf'),

]