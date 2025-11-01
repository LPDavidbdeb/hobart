from django.db.models.signals import post_save
from django.dispatch import receiver
from address.models import Address
from .models import NestedTerritory
from unidecode import unidecode

def _normalize_name(name):
    if not name: return None
    return unidecode(name).strip().lower()

@receiver(post_save, sender=Address)
def update_nested_territory_on_address_save(sender, instance, created, **kwargs):
    """
    Signal receiver that creates or updates a NestedTerritory leaf node
    whenever an Address object is saved.
    Skips execution if the save is part of a raw data load (e.g., loaddata).
    """
    if kwargs.get('raw'):
        return

    address = instance

    # First, find if a node for this address already exists and delete it.
    # This handles both updates and ensures we don't create duplicates.
    NestedTerritory.objects.filter(source_address=address).delete()

    # If the address is degenerate, we stop here. We don't want it in the tree.
    if address.is_degenerate():
        return

    # --- Find or Create the hierarchy for this address ---
    try:
        # Start with the root
        parent_node = NestedTerritory.objects.get(type=NestedTerritory.TerritoryType.COUNTRY)

        # Define the path components for this address
        path_components = []
        province_name = _normalize_name(address.get_component('administrative_area_level_1'))
        region_name = _normalize_name(address.get_component('administrative_area_level_2'))
        city_name = _normalize_name(address.get_component('locality', fallback_types=['administrative_area_level_3', 'sublocality']))
        postal_code_full = _normalize_name(address.get_component('postal_code'))
        fsa_code = postal_code_full[:3] if postal_code_full and len(postal_code_full) >= 3 else None
        formatted_address = address.formatted

        if province_name: path_components.append((province_name, NestedTerritory.TerritoryType.PROVINCE))
        if region_name: path_components.append((region_name, NestedTerritory.TerritoryType.REGION))
        if city_name: path_components.append((city_name, NestedTerritory.TerritoryType.CITY))
        if fsa_code: path_components.append((fsa_code, NestedTerritory.TerritoryType.FSA))
        if postal_code_full and postal_code_full != fsa_code:
            path_components.append((postal_code_full, NestedTerritory.TerritoryType.POSTAL_CODE))
        
        # Traverse the tree, creating nodes as needed
        for name, node_type in path_components:
            parent_node, _ = NestedTerritory.objects.get_or_create(
                name=name,
                type=node_type,
                parent=parent_node
            )

        # Finally, create the ADDRESS leaf node
        if formatted_address:
            NestedTerritory.objects.create(
                name=formatted_address,
                type=NestedTerritory.TerritoryType.ADDRESS,
                parent=parent_node,
                source_address=address
            )

    except NestedTerritory.DoesNotExist:
        # This can happen if the root 'Canada' node doesn't exist. 
        # In this case, we can't build the tree for this address.
        # You might want to log this as a warning.
        print(f"Warning: Could not find root COUNTRY node. Cannot update NestedTerritory for Address ID {address.id}.")
    except Exception as e:
        # Catch any other unexpected errors during the process
        print(f"Error updating NestedTerritory for Address ID {address.id}: {e}")
