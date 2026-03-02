from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("manager/billing/", views.billing_dashboard,name="billing_dashboard"),

    path('toggle_bill_status/<int:bill_id>/', views.toggle_bill_status, name='toggle_bill_status'),
    
    path('delete_bill/<int:bill_id>/', views.delete_bill, name='delete_bill'),
   
]