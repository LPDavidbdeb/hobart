from django.urls import path
from .views import (
    UserCreateView,
    UserDetailView,
    UserUpdateView,
    UserDeleteView,
)

app_name = 'users'

urlpatterns = [
    # The user_list URL has been removed. The main list is now in the 'employees' app.
    path('create/', UserCreateView.as_view(), name='user_create'),
    path('<int:pk>/', UserDetailView.as_view(), name='user_detail'),
    path('<int:pk>/update/', UserUpdateView.as_view(), name='user_update'),
    path('<int:pk>/delete/', UserDeleteView.as_view(), name='user_delete'),
]
