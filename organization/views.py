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
    # --- NEW: Get root nodes (level=0) for the dropdown ---
    root_territories = list(NestedTerritory.objects
                            .filter(level=0)
                            .values_list('name', flat=True)
                            .order_by('name'))

    # Determine the default and selected tree from the root territory names
    default_root_name = root_territories[0] if root_territories else None
    selected_root_name = request.GET.get('tree', default_root_name)
    # --- END NEW ---

    initial_nodes = []
    # Find the root node based on the *selected name*
    root_node = NestedTerritory.objects.filter(name=selected_root_name, level=0).first()

    if root_node:
        # If the root itself has children, display them. Otherwise, display the root.
        children = root_node.get_children()
        if children:
            initial_nodes = [node.to_json() for node in children]
        else:
            # If the root is a leaf (like 'Yukon'), it has no children to show,
            # so we show the node itself in the visualization.
            initial_nodes = [root_node.to_json()]

    return render(request, 'organization/territory_explorer.html', {
        # Pass the list of root names to the template
        'tree_names': root_territories,
        # Pass the selected root name as the default
        'default_tree': selected_root_name,
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


import json
import time
from django.shortcuts import render
from .models import NestedTerritory


import json
import time
from django.shortcuts import render
from .models import NestedTerritory

def province_map_view(request):
    # 1. Fast Fetch
    # We ONLY fetch the small 'simplified_boundary' field.
    # We DEFER the huge 'boundary' field so it never touches standard memory.
    provinces = NestedTerritory.objects.filter(
        type=NestedTerritory.TerritoryType.PROVINCE,
        simplified_boundary__isnull=False
    ).defer('boundary')

    # 2. Zero-Processing Serialization
    features = []
    for province in provinces:
        features.append({
            "type": "Feature",
            "properties": {
                "id": province.id,
                "name": province.name,
                "client_count": province.client_count
            },
            # Just load the pre-calculated JSON string. No math required.
            "geometry": json.loads(province.simplified_boundary.json)
        })

    # province_geojson = json.dumps({"type": "FeatureCollection", "features": features})
    province_geojson = {"type": "FeatureCollection", "features": features}

    context = {
        "centroid": [56.13, -106.35], # Center of Canada
        "zoom": 3,
        "province_geojson": province_geojson
    }

    return render(request, "organization/province_map.html", context)