from django.urls import path
from . import views

app_name = 'employees'

urlpatterns = [
    path('', views.EmployeeListView.as_view(), name='employee_list'),
    path('<int:pk>/', views.EmployeeDetailView.as_view(), name='employee_detail'),
    path('upload-csv/', views.upload_csv_view, name='upload_csv'),
    path('api/update-field/', views.update_employee_field_api, name='update_employee_field_api'),
    # The new API for live table filtering
    path('api/search-filter/', views.employee_search_and_filter_api, name='employee_search_filter_api'),
]
