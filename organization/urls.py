from django.urls import path
from . import views

app_name = 'organization'

urlpatterns = [
    path('territory-tree/', views.nested_territory_tree_view, name='nested_territory_tree'),
    path('territory-tree/json/', views.nested_territory_json_api, name='nested_territory_json_api'),
]
