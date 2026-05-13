from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("manager/billing/", views.billing_dashboard,name="billing_dashboard"),

    path("record-payment/<int:bill_id>/", views.record_payment, name="record_payment"),
    
    path('delete_bill/<int:bill_id>/', views.delete_bill, name='delete_bill'),
   
    path('manager/billing/pdf/', views.billing_pdf, name='billing_pdf'),

]