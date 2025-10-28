from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Address
from organization.models import Territory
from client.models import Client

@receiver(post_save, sender=Address)
def create_and_assign_territories(sender, instance, created, **kwargs):
    """Signal to create territories from address data and assign them to clients."""
    if not instance.postal_code: # Only process addresses with enough data
        return

    territory_data = {
        'PROVINCE': instance.administrative_area_level_1,
        'REGION': instance.administrative_area_level_2,
        'CITY': instance.locality,
    }

    primary_territory = None

    for territory_type, territory_name in territory_data.items():
        if territory_name:
            territory, _ = Territory.objects.get_or_create(
                name=territory_name,
                type=territory_type
            )
            # We will assign the most specific territory available (City > Region > Province)
            primary_territory = territory

    # If a territory was found/created, find related clients and assign it.
    if primary_territory:
        # Find clients directly linked to this address
        clients_to_update = Client.objects.filter(address=instance)
        for client in clients_to_update:
            client.territory = primary_territory
            client.save() # Note: This will re-trigger signals, be mindful of loops if any
