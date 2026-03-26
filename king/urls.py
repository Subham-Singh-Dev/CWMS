from django.urls import path
from . import views

app_name = 'king'

urlpatterns = [
    # Secret URL — only contractor knows this
    path('secure/owner-x7k2/', views.king_login, name='king_login'),
    
    path('king/dashboard/', views.king_dashboard, name='king_dashboard'),

    path('king/logout/', views.king_logout, name='king_logout'),

    # Work Orders (add later)
    # Revenue (add later)
    # Ledger (add later)
]