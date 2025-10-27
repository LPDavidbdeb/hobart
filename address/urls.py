from django.urls import path
from . import views

app_name = 'address'

urlpatterns = [
    # Dashboard
    path('health-dashboard/', views.AddressHealthDashboardView.as_view(), name='health_dashboard'),

    # APIs
    path('api/search/', views.search_address_api, name='search_address_api'),
    path('api/set-employee-address/', views.set_employee_address_api, name='set_employee_address_api'),
    path('api/set-client-address/', views.set_client_address_api, name='set_client_address_api'),
]
