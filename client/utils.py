import os
from DAO.adresses_DAO import GoogleMapsClient
from address.models import Address, AddressStatus
from client.models import Client # Import Client model

def update_client_address_from_place_details(client_instance: Client, place_id: str):
    """
    Fetches full Google Place Details for a given place_id, saves/updates the Address model,
    and associates it with the client instance, setting the appropriate AddressStatus.
    
    Args:
        client_instance (Client): The client object to update.
        place_id (str): The Google Place ID for the desired address.
        
    Returns:
        Client: The updated client instance.
    """
    gmaps_client = GoogleMapsClient()
    place_details_results = gmaps_client.geocode_by_place_id(place_id)

    if not place_details_results:
        # If Place Details cannot be retrieved, mark as MISSING
        address_status_missing = AddressStatus.objects.get(name='MISSING')
        client_instance.address = None
        client_instance.address_status = address_status_missing
        client_instance.save(update_fields=['address', 'address_status'])
        raise ValueError("Could not retrieve details for the selected address.")

    address_obj, created = Address.save_from_google_maps_data(place_details_results[0])

    if not address_obj:
        raise ValueError("Failed to save address data from Google Place Details.")

    # Determine AddressStatus based on degeneracy
    if address_obj.is_degenerate():
        address_status_incomplete = AddressStatus.objects.get(name='INCOMPLETE')
        client_instance.address_status = address_status_incomplete
    else:
        address_status_complete = AddressStatus.objects.get(name='COMPLETE')
        client_instance.address_status = address_status_complete

    client_instance.address = address_obj
    client_instance.save(update_fields=['address', 'address_status'])
    
    return client_instance


def process_client_csv(file):
    # This function will be moved/modified in client/views.py
    pass

def process_dimension_csv(file, dimension_type):
    # This function will be moved/modified in client/views.py
    pass

def process_client_group_csv(file):
    # This function will be moved/modified in client/views.py
    pass
