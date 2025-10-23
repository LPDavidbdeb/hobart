"""
URL configuration for Hobart project.
"""
from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # The main entry point for all employee-related views
    path('employees/', include('employees.urls', namespace='employees')),

    # The new entry point for all client-related views
    path('clients/', include('client.urls', namespace='client')),
    
    # Keep user-specific actions like create, update, delete under a separate path
    path('users/', include('users.urls', namespace='users')),
    
    path('logout/', views.logout_view, name='logout'),
    path('home/', views.personalized_home_view, name='personalized_home'),
    path('', views.home_view, name='home'),
]
