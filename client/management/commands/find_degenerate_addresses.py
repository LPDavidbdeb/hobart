import re
from django.core.management.base import BaseCommand
from django.db.models import Q
from address.models import Address
from client.models import Client

class Command(BaseCommand):
    help = 'Finds clients with degenerate addresses where the original address1 seems valid.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("--- Starting Focused Analysis of Degenerate Addresses ---"))

        # 1. Find addresses degenerate specifically because of missing street number or route
        degenerate_addresses = Address.objects.filter(
            Q(street_number__isnull=True) | Q(route__isnull=True)
        )

        if not degenerate_addresses.exists():
            self.stdout.write(self.style.SUCCESS("No addresses found with NULL street_number or route."))
            return

        # 2. Find clients linked to this specific type of degenerate address
        clients_to_check = Client.objects.filter(
            address__in=degenerate_addresses
        ).select_related('address')

        self.stdout.write(f"Found {clients_to_check.count()} clients linked to addresses with missing street/route. Analyzing original address1 field...")

        # 3. Define the regex for 'number space letters'
        # Allows for multi-word street names and is case-insensitive
        pattern = re.compile(r'^\d+\s+[a-zA-Z\s\'.-]+$', re.IGNORECASE)
        
        cases_of_interest = []
        for client in clients_to_check:
            # 4. Check if address1 is not empty and matches the pattern
            if client.address1 and pattern.match(client.address1.strip()):
                cases_of_interest.append(client)

        # 5. Print the final report
        if not cases_of_interest:
            self.stdout.write(self.style.WARNING("\nNo clients found where the original 'address1' matched the pattern 'number space name' but the geocoded result was degenerate."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n--- Report: Found {len(cases_of_interest)} Cases of Interest ---"))
            self.stdout.write("The following clients have an 'address1' that looks valid, but the geocoded result is missing a street number or name.")
            
            for client in cases_of_interest:
                missing_fields = []
                if not client.address.street_number: missing_fields.append('street_number')
                if not client.address.route: missing_fields.append('route')

                self.stdout.write("\n--------------------------------------------------")
                self.stdout.write(self.style.SQL_KEYWORD(f"Client Name: {client.name}"))
                self.stdout.write(f"  Original Address 1: {client.address1} {self.style.SUCCESS('(MATCHES PATTERN)')}")
                self.stdout.write(f"  Original Address 2: {client.address2}")
                self.stdout.write(self.style.WARNING(f"  Problematic Formatted Address: {client.address.formatted}"))
                self.stdout.write(self.style.ERROR(f"  Missing Fields: {', '.join(missing_fields)}"))
                self.stdout.write("--------------------------------------------------")

        self.stdout.write(self.style.SUCCESS("\n--- Analysis Complete ---"))
