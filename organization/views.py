from django.shortcuts import render
from django.http import JsonResponse
from .models import NestedTerritory

def nested_territory_tree_view(request):
    return render(request, 'organization/nested_territory_tree.html')

def nested_territory_json_api(request):
    node_id = request.GET.get('node_id')

    if node_id:
        try:
            parent = NestedTerritory.objects.get(pk=node_id)
            nodes = parent.get_children()
        except NestedTerritory.DoesNotExist:
            return JsonResponse([], safe=False)
        
        data = []
        for node in nodes:
            data.append({
                'id': node.pk,
                'name': node.name,
                'hasChildren': not node.is_leaf_node(),
            })
        return JsonResponse(data, safe=False)
    else:
        # For the initial load, d3.hierarchy expects a single root node.
        # We'll create a virtual root node.
        root_nodes = NestedTerritory.objects.filter(level=0)
        children = []
        for node in root_nodes:
            children.append({
                'id': node.pk,
                'name': node.name,
                'hasChildren': not node.is_leaf_node(),
            })
        
        # The d3 script expects a single root object for the initial data load
        root_data = {
            "name": "Territories",
            "id": "root",
            "children": children
        }
        return JsonResponse(root_data)
