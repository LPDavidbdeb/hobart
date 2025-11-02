from django.shortcuts import render
from django.http import JsonResponse
from .models import NestedTerritory


def nested_territory_tree_view(request):
    # --- CHANGED ---
    # Get all distinct tree names to pass to the template for the dropdown
    tree_names = list(
        NestedTerritory.objects.values_list('tree_name', flat=True).distinct().order_by('tree_name')
    )
    context = {
        'tree_names': tree_names
    }
    return render(request, 'organization/nested_territory_tree.html', context)
    # --- END CHANGED ---


def nested_territory_json_api(request):
    node_id = request.GET.get('node_id')
    tree_name = request.GET.get('tree_name')  # Get the selected tree name

    if node_id:
        # This logic is for lazy-loading children and remains the same
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

    # --- CHANGED ---
    # This is the initial load for a *specific tree*
    elif tree_name:
        try:
            # Find the root node (level 0) for the selected tree
            tree_root = NestedTerritory.objects.get(tree_name=tree_name, level=0)

            # Get its immediate children (e.g., "Canada")
            children_nodes = tree_root.get_children()
            children_data = []
            for node in children_nodes:
                children_data.append({
                    'id': node.pk,
                    'name': node.name,
                    'hasChildren': not node.is_leaf_node(),
                })

            # Return the tree's root node (e.g., "Administrative") as the *new*
            # root for the D3.js hierarchy.
            root_data = {
                "name": tree_root.name,  # e.g., "Administrative"
                "id": tree_root.pk,
                "children": children_data
            }
            return JsonResponse(root_data)

        except NestedTerritory.DoesNotExist:
            return JsonResponse({"error": f"No root node found for tree: {tree_name}"}, status=404)
        except NestedTerritory.MultipleObjectsReturned:
            return JsonResponse({"error": f"Multiple root nodes found for tree: {tree_name}"}, status=500)
    # --- END CHANGED ---

    else:
        # Fallback if no tree_name is provided
        return JsonResponse({"error": "No tree_name specified"}, status=400)