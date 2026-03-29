from django.urls import path
from . import views

app_name = 'king'

urlpatterns = [
    # Secret URL — only contractor knows this
    path('secure/owner-x7k2/', views.king_login, name='king_login'),
    
    path('dashboard/', views.king_dashboard, name='king_dashboard'),

    path('logout/', views.king_logout, name='king_logout'),

    #workorder
    # Work Orders
    path('workorders/',                      views.workorder_dashboard,    name='workorder_dashboard'),
    path('workorders/add/',                  views.workorder_add,          name='workorder_add'),
    path('workorders/<int:wo_id>/',          views.workorder_detail,       name='workorder_detail'),
    path('workorders/<int:wo_id>/edit/',     views.workorder_edit,         name='workorder_edit'),
    path('workorders/<int:wo_id>/status/',   views.workorder_status_update,name='workorder_status_update'),

   
    # Revenue
    path('revenue/',                         views.revenue_dashboard,      name='revenue_dashboard'),
    path('revenue/add/',                     views.revenue_add,            name='revenue_add'),
    path('revenue/delete/<int:rev_id>/',     views.revenue_delete,         name='revenue_delete'),
    
    #ledger
    path('ledger/',                          views.ledger_view,         name='ledger'),
    path('ledger/add/',                      views.ledger_add_entry,    name='ledger_add'),
    path('ledger/delete/<int:entry_id>/',    views.ledger_delete_entry, name='ledger_delete'),
    path('ledger/pdf/',                      views.ledger_pdf,          name='ledger_pdf'),
]