"""
URL configuration for Hobart project.
"""
from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # App-specific URL includes
    # --- THIS IS THE FIX ---
    # The "namespace" argument is removed from all includes.
    # The namespace will now be automatically picked up
    # from the app_name in each app's urls.py file.

    path('employees/', include('employees.urls')),
    path('clients/', include('client.urls')),
    path('users/', include('users.urls')),
    path('address/', include('address.urls')),
    path('organization/', include('organization.urls')),
    path('', include('core.urls')), # Added core app URLs

    # Project-level views
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('home/', views.personalized_home_view, name='personalized_home'),
    # Note: The root path '' is now handled by the core app.
]