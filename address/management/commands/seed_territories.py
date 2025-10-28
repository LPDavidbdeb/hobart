import json
from django.core.management.base import BaseCommand
from address.models import Address
from organization.models import Territory
from client.models import Client
from django.db import transaction

class Command(BaseCommand):
    help = 'Seeds Territory data from existing Address objects.'

    def handle(self, *args, **options):
        self.stdout.write("Starting to seed territories from existing addresses...")
        
        address_count = 0
        territory_count = 0
        client_count = 0

        with transaction.atomic():
            for address in Address.objects.filter(raw_response__isnull=False).iterator():
                address_count += 1
                
                try:
                    raw_data = address.raw_response
                    # Corrected: address_components is directly under raw_data
                    address_components = raw_data.get('address_components', [])
                except AttributeError:
                    self.stdout.write(self.style.WARNING(f"Skipping address {address.id} due to malformed raw_response structure (missing address_components)."))
                    continue

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
                        if created:
                            territory_count += 1
                        # The most specific one found will be the primary
                        primary_territory = territory
                        break # Assign only the most specific one found

                # If a territory was found/created, find related clients and assign it.
                if primary_territory:
                    clients_to_update = Client.objects.filter(address=address)
                    for client in clients_to_update:
                        if client.territory != primary_territory:
                            client.territory = primary_territory
                            client.save()
                            client_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully processed {address_count} addresses. "
            f"Created {territory_count} new territories. "
            f"Updated {client_count} clients."
        ))
