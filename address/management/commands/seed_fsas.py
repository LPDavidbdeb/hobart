from django.core.management.base import BaseCommand
from address.models import Address, FSA
from django.db import transaction

class Command(BaseCommand):
    help = 'Seeds FSA data from existing Address objects.'

    def handle(self, *args, **options):
        self.stdout.write("Starting to seed FSAs from existing addresses...")
        
        processed_count = 0
        created_count = 0

        with transaction.atomic():
            # Get all unique FSAs and their most common city from existing addresses
            # This is more efficient than iterating through every single address
            fsa_data = {}
            for address in Address.objects.filter(raw_response__isnull=False).iterator():
                postal_code = address.postal_code
                if postal_code and len(postal_code) >= 3:
                    fsa_code = postal_code[:3]
                    city = address.city
                    if fsa_code not in fsa_data:
                        fsa_data[fsa_code] = {}
                    if city:
                        fsa_data[fsa_code][city] = fsa_data[fsa_code].get(city, 0) + 1
                processed_count += 1

            # Now, create the FSA objects
            for fsa_code, cities in fsa_data.items():
                # Use the most frequent city as the description
                description = max(cities, key=cities.get) if cities else ''
                
                _, created = FSA.objects.get_or_create(
                    code=fsa_code,
                    defaults={'description': description}
                )
                if created:
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully processed {processed_count} addresses. "
            f"Found {len(fsa_data)} unique FSAs. "
            f"Created {created_count} new FSA entries."
        ))
