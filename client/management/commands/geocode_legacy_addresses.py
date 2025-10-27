import time
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from client.models import Client
from DAO.adresses_DAO import GoogleMapsClient

class Command(BaseCommand):
    help = 'Geocodes legacy address fields and links clients to standardized Address objects.'

    def handle(self, *args, **options):
        if not settings.GOOGLE_MAPS_API_KEY:
            raise CommandError('GOOGLE_MAPS_API_KEY is not configured in your settings.')

        gmaps_client = GoogleMapsClient()
        clients_to_process = Client.objects.filter(address__isnull=True).exclude(address1='', address2='')

        total_clients = clients_to_process.count()
        if total_clients == 0:
            self.stdout.write(self.style.SUCCESS('No clients to process. All clients already have a standardized address or no legacy address data.'))
            return

        self.stdout.write(f'Found {total_clients} clients to geocode.')

        success_count = 0
        fail_count = 0

        for i, client in enumerate(clients_to_process):
            # Construct a full address string for geocoding
            address_parts = [client.address1, client.address2, client.postal_code]
            full_address = ", ".join(part.strip() for part in address_parts if part and part.strip())

            if not full_address:
                self.stdout.write(self.style.WARNING(f'Skipping client {client.account_number} due to empty legacy address fields.'))
                continue

            self.stdout.write(f'({i+1}/{total_clients}) Processing client: {client.account_number} - {full_address}')

            try:
                # Geocode the address and save the new Address object
                address_obj = gmaps_client.geocode_and_save(full_address)

                if address_obj:
                    # Link the new Address object to the client
                    client.address = address_obj
                    client.save(update_fields=['address'])
                    self.stdout.write(self.style.SUCCESS(f'  -> Successfully linked to Address: {address_obj.place_id}'))
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f'  -> Geocoding failed for address: {full_address}'))
                    fail_count += 1
                
                # Google Maps API has a rate limit (e.g., 50 QPS). A small delay prevents hitting it.
                time.sleep(0.05) # 50ms delay

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  -> An unexpected error occurred: {e}'))
                fail_count += 1

        self.stdout.write(self.style.SUCCESS('\nGeocoding process complete!'))
        self.stdout.write(f'Successfully processed: {success_count}')
        self.stdout.write(f'Failed to process: {fail_count}')
