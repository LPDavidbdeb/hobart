import json
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Address
from organization.models import Territory
from client.models import Client

@receiver(post_save, sender=Address)
def create_and_assign_territories(sender, instance, created, **kwargs):
    """Signal to create territories from address data and assign them to clients."""
    if not instance.raw_response: 
        return

    try:
        raw_data = instance.raw_response
        address_components = raw_data.get('address_components', [])
    except AttributeError:
        # Log this error in production, for now just return
        return

    province_name = None
    region_name = None
    city_name = None

    for component in address_components:
        types = component.get('types', [])
        if 'administrative_area_level_1' in types: # Province
            province_name = component.get('long_name')
        elif 'administrative_area_level_2' in types: # Region/RCM
            region_name = component.get('long_name')
        elif 'locality' in types: # City
            city_name = component.get('long_name')
    
    territory_data = {
        'PROVINCE': province_name,
        'REGION': region_name,
        'CITY': city_name,
    }

    primary_territory = None

    # Process in order of specificity (City, then Region, then Province)
    for territory_type_key in ['CITY', 'REGION', 'PROVINCE']:
        territory_name = territory_data.get(territory_type_key)
        if territory_name:
            territory, created = Territory.objects.get_or_create(
                name=territory_name,
                type=territory_type_key
            )
            primary_territory = territory
            break # Assign only the most specific one found

    # If a territory was found/created, find related clients and assign it.
    if primary_territory:
        clients_to_update = Client.objects.filter(address=instance)
        for client in clients_to_update:
            if client.territory != primary_territory:
                client.territory = primary_territory
                client.save() # Note: This will re-trigger signals, be mindful of loops if any
