from django.urls import path
from . import views

app_name = 'employees'

urlpatterns = [
    path('', views.EmployeeListView.as_view(), name='employee_list'),
    
    # Role-specific lists using the generic view
    path('directors/', views.DirectorListView.as_view(), name='director_list'),
    path('managers/', views.ManagerListView.as_view(), name='manager_list'),
    path('technicians/', views.TechnicianListView.as_view(), name='technician_list'),

    # Detail, Edit, and Upload URLs
    path('edit/<int:pk>/', views.edit_employee_view, name='edit_employee'),
    path('<int:pk>/', views.EmployeeDetailView.as_view(), name='employee_detail'),
    path('upload-csv/', views.upload_csv_view, name='upload_csv'),

    # API endpoints
    path('api/update-field/', views.update_employee_field_api, name='update_employee_field_api'),
    path('api/search-filter/', views.employee_search_and_filter_api, name='employee_search_filter_api'),
]
