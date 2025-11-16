from django.urls import path
from . import views

app_name = 'routing'

urlpatterns = [
    path('find-technician/<int:client_id>/', views.find_best_technician_view, name='find_best_technician'),
    path('api/calculate-route/', views.calculate_route_api, name='calculate_route_api'),
]
