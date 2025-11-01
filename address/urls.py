from django.urls import path
from . import views

app_name = 'address'

urlpatterns = [
    # FSA Search
    path('fsa-search/', views.FSASearchView.as_view(), name='fsa_search'),

    # Dashboard
    path('health-dashboard/', views.AddressHealthDashboardView.as_view(), name='health_dashboard'),

    # APIs
    path('api/fsa-autocomplete/', views.fsa_autocomplete_api, name='fsa_autocomplete_api'),
    path('api/search/', views.search_address_api, name='search_address_api'),
    path('api/set-employee-address/', views.set_employee_address_api, name='set_employee_address_api'),
    path('api/set-client-address/', views.set_client_address_api, name='set_client_address_api'),
    path('api/get-territory-fsas/<int:territory_id>/', views.get_territory_fsas_api, name='get_territory_fsas_api'),
]
