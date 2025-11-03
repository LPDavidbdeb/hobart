from django.core.management.base import BaseCommand
from django.db import transaction
from address.models import FSA, Address
from client.models import Client
from collections import Counter
from django.contrib.gis.geos import MultiPoint, MultiPolygon
from django.db.models import Q

class Command(BaseCommand):
    help = 'Calculates client counts for each FSA, creating and inferring boundaries for new FSAs.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Starting to update client counts and infer FSA boundaries...")

        # Step 1: Reset counts
        self.stdout.write("  -> Resetting client counts for all FSAs...")
        FSA.objects.update(client_count=0)

        # Step 2: Get valid clients and their locations
        self.stdout.write("  -> Fetching active clients with valid, non-degenerate addresses...")
        clients_with_locations = Client.objects.select_related('address').filter(
            address__isnull=False, 
            address__location__isnull=False
        )

        fsa_client_map = {}
        clients_processed = 0
        clients_skipped = 0

        # Step 3: Group clients by FSA
        self.stdout.write("  -> Grouping clients by FSA...")
        for client in clients_with_locations.iterator():
            address = client.address
            if address and not address.is_degenerate() and address.postal_code:
                fsa_code = address.postal_code[:3].upper()
                if fsa_code not in fsa_client_map:
                    fsa_client_map[fsa_code] = []
                fsa_client_map[fsa_code].append(client)
                clients_processed += 1
            else:
                clients_skipped += 1
        self.stdout.write(f"     Processed {clients_processed} clients. Skipped {clients_skipped} clients.")

        # Step 4: Create missing FSAs
        self.stdout.write(f"  -> Checking for {len(fsa_client_map)} unique FSAs...")
        existing_fsa_codes = set(FSA.objects.values_list('code', flat=True))
        missing_fsa_codes = set(fsa_client_map.keys()) - existing_fsa_codes

        if missing_fsa_codes:
            self.stdout.write(self.style.WARNING(f"     Found {len(missing_fsa_codes)} new FSAs. Creating them now..."))
            new_fsas = []
            for code in missing_fsa_codes:
                clients_in_fsa = fsa_client_map[code]
                points = MultiPoint([client.address.location for client in clients_in_fsa if client.address.location])
                
                new_fsa = FSA(
                    code=code, 
                    description="Inferred from client data.",
                    source=FSA.Source.INFERRED,
                    client_count=len(clients_in_fsa)
                )

                if len(points) >= 3:
                    inferred_boundary = points.convex_hull
                    if inferred_boundary.geom_type == 'Polygon':
                        new_fsa.boundary = MultiPolygon(inferred_boundary)
                        new_fsa.boundary_type = FSA.BoundaryType.INFERRED_CONVEX_HULL
                
                new_fsas.append(new_fsa)

            FSA.objects.bulk_create(new_fsas)
            self.stdout.write(self.style.SUCCESS(f"     Successfully created {len(new_fsas)} new FSA records with inferred data."))

        # Step 5: Update counts for existing FSAs
        self.stdout.write("  -> Updating counts for existing FSAs...")
        fsas_to_update = []
        existing_fsas = FSA.objects.filter(code__in=fsa_client_map.keys())

        for fsa in existing_fsas:
            fsa.client_count = len(fsa_client_map[fsa.code])
            fsas_to_update.append(fsa)

        if fsas_to_update:
            FSA.objects.bulk_update(fsas_to_update, ['client_count'], batch_size=500)
            self.stdout.write(self.style.SUCCESS(f"     Successfully updated {len(fsas_to_update)} existing FSA records."))

        self.stdout.write(self.style.SUCCESS("\nProcess Finished! FSA data is now fully updated."))
