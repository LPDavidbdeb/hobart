"""
URL configuration for Hobart project.
"""
from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # App-specific URL includes
    path('employees/', include('employees.urls', namespace='employees')),
    path('clients/', include('client.urls', namespace='client')),
    path('users/', include('users.urls', namespace='users')),
    path('address/', include('address.urls', namespace='address')),
    path('', include('core.urls', namespace='core')), # Added core app URLs

    # Project-level views
    path('logout/', views.logout_view, name='logout'),
    path('home/', views.personalized_home_view, name='personalized_home'),
    # Note: The root path '' is now handled by the core app.
    # You might want to move the home_view to the core app as well.
]
