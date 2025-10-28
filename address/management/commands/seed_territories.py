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
            for address in Address.objects.filter(postal_code__isnull=False).iterator():
                address_count += 1
                territory_data = {
                    'PROVINCE': address.administrative_area_level_1,
                    'REGION': address.administrative_area_level_2,
                    'CITY': address.locality,
                }

                primary_territory = None

                for territory_type, territory_name in territory_data.items():
                    if territory_name:
                        territory, created = Territory.objects.get_or_create(
                            name=territory_name,
                            type=territory_type
                        )
                        if created:
                            territory_count += 1
                        primary_territory = territory
                
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
