from django.urls import path
from . import views

app_name = 'organization'

urlpatterns = [
    # DELETE your old 'territory-tree/' path
    # path('territory-tree/', views.nested_territory_tree_view, name='nested_territory_tree'),

    # ADD THIS: The page that hosts the D3 visualization
    path('territory-explorer/',
         views.territory_explorer_page,
         name='territory_explorer_page'),

    # ADD THIS: The API endpoint that D3 will call to get child nodes
    path('api/territory-children/',
         views.territory_children_api,
         name='territory_children_api'),
]