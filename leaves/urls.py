from django.urls import path
from . import views

urlpatterns = [
    path('assign/', views.assign_leave_view, name='assign_leave'),
    path('list/', views.leave_list_view, name='leave_list'),
    path('pdf/<int:leave_id>/', views.generate_leave_pdf_view, name='leave_pdf'),
]