from django.urls import path
from . import views

app_name = 'client'

urlpatterns = [
    # Main Client Views
    path('list/', views.ClientListView.as_view(), name='client_list'),
    path('detail/<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('api/client-search-filter/', views.client_search_and_filter_api, name='client_search_filter_api'),

    # Client Group Views
    path('groups/', views.ClientGroupListView.as_view(), name='clientgroup_list'),
    path('groups/create/', views.ClientGroupCreateView.as_view(), name='clientgroup_create'),
    path('groups/<int:pk>/', views.ClientGroupDetailView.as_view(), name='clientgroup_detail'),
    path('api/group-search-filter/', views.client_group_search_and_filter_api, name='group_search_filter_api'),
    path('api/group-update-field/', views.update_client_group_field_api, name='group_update_field_api'),

    # Upload Views
    path('upload-group/', views.upload_client_group_view, name='upload_group_csv'),
    path('upload-dimension/', views.upload_dimension_view, name='upload_dimension'),
    path('upload-client/', views.upload_client_view, name='upload_client'),
]
