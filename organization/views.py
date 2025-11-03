from django.shortcuts import render
from django.http import JsonResponse
from .models import NestedTerritory
import json


# --- DELETE your old nested_territory_tree_view ---

# --- ADD THIS NEW VIEW ---
def territory_explorer_page(request):
    """
    Renders the main page with the D3 visualization.
    """
    tree_names = list(NestedTerritory.objects
                      .values_list('tree_name', flat=True)
                      .distinct()
                      .order_by('tree_name'))

    default_tree = tree_names[0] if tree_names else 'Default'

    # --- THIS IS THE CHANGE ---
    # Check if a tree is specified in the URL, otherwise use default
    selected_tree = request.GET.get('tree', default_tree)
    # --- END OF CHANGE ---

    initial_nodes = []
    # Find the root node for the *selected* tree
    root_node = NestedTerritory.objects.filter(tree_name=selected_tree, level=0).first()

    if root_node:
        initial_nodes = [node.to_json() for node in root_node.get_children()]

    return render(request, 'organization/territory_explorer.html', {
        'tree_names': tree_names,
        'default_tree': selected_tree,  # Pass the selected tree as the default
        'initial_data_json': json.dumps(initial_nodes),
    })


# --- ADD THIS NEW API VIEW ---
def territory_children_api(request):
    """
    API endpoint to fetch child nodes for lazy-loading.
    """
    try:
        # Get the ID of the node the user clicked on
        parent_id = request.GET.get('parent_id')

        # This is the core of the efficient query
        parent_node = NestedTerritory.objects.get(id=parent_id)

        # get_children() is a highly efficient MPTT method.
        # It only fetches the *immediate* children (a simple, indexed query).
        nodes = parent_node.get_children()

        # Serialize only those children to JSON
        data = [node.to_json() for node in nodes]
        return JsonResponse(data, safe=False)

    except NestedTerritory.DoesNotExist:
        return JsonResponse({'error': 'Node not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)