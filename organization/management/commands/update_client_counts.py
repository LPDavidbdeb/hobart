from django.core.management.base import BaseCommand
from django.db import transaction, connection
from organization.models import NestedTerritory
from client.models import Client
from address.models import Address # Import Address model
from django.db.models import Count, Sum

class Command(BaseCommand):
    help = 'Calculates and stores the number of clients for each node in the NestedTerritory tree.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output for debugging.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        verbose = options['verbose']
        self.stdout.write("Starting to update client counts for all territory nodes...")

        # Reset all counts to zero before starting
        self.stdout.write("  -> Resetting all existing counts to 0...")
        NestedTerritory.objects.update(client_count=0)

        # Step 0: Identify non-degenerate address place_ids
        self.stdout.write("Step 0: Identifying non-degenerate addresses...")
        non_degenerate_place_ids = set()
        degenerate_count = 0
        for addr in Address.objects.filter(place_id__isnull=False).iterator():
            if not addr.is_degenerate():
                non_degenerate_place_ids.add(addr.place_id)
                if verbose and len(non_degenerate_place_ids) % 1000 == 0:
                    self.stdout.write(f"    ... added {len(non_degenerate_place_ids)} non-degenerate place_ids ...")
            else:
                degenerate_count += 1
        self.stdout.write(self.style.SUCCESS(f"Step 0 Complete: Found {len(non_degenerate_place_ids)} non-degenerate place_ids. ({degenerate_count} degenerate addresses skipped)"))

        # Step 1: Set the count for all ADDRESS leaf nodes
        self.stdout.write("Step 1: Calculating counts for ADDRESS leaf nodes...")
        # Correctly filter for ADDRESS nodes that have at least one linked address.
        address_nodes = NestedTerritory.objects.filter(type=NestedTerritory.TerritoryType.ADDRESS, addresses__isnull=False).distinct()
        nodes_to_update = []
        count = 0
        clients_found_in_step1 = 0

        for node in address_nodes.iterator():
            # Get the first linked address for this node.
            # For an ADDRESS-type territory, we assume there's only one.
            source_address = node.addresses.first()
            current_node_client_count = 0

            if source_address and source_address.place_id:
                if source_address.place_id in non_degenerate_place_ids:
                    # Count clients linked to this specific address's place_id
                    current_node_client_count = Client.objects.filter(address__place_id=source_address.place_id).count()
                    if current_node_client_count > 0:
                        clients_found_in_step1 += current_node_client_count
                        if verbose:
                            self.stdout.write(f"      -> Node '{node.name}' (ID: {node.id}, PlaceID: {source_address.place_id}) has {current_node_client_count} clients.")
                elif verbose:
                    self.stdout.write(f"      -> Node '{node.name}' (ID: {node.id}, PlaceID: {source_address.place_id}) skipped (degenerate address).")
            elif verbose:
                self.stdout.write(f"      -> Node '{node.name}' (ID: {node.id}) skipped (missing source_address or place_id).")
            
            node.client_count = current_node_client_count
            nodes_to_update.append(node)
            count += 1
            if count % 2000 == 0:
                self.stdout.write(f"    ... processed {count} address nodes ...")
        
        if nodes_to_update:
            NestedTerritory.objects.bulk_update(nodes_to_update, ['client_count'], batch_size=2000)
        self.stdout.write(self.style.SUCCESS(f"Step 1 Complete: Updated counts for {count} address nodes. Total clients directly linked: {clients_found_in_step1}."))

        # Step 2: Roll up the counts from the bottom of the tree to the top
        self.stdout.write("Step 2: Rolling up counts from leaves to root...")
        max_level_obj = NestedTerritory.objects.order_by('-level').first()
        if not max_level_obj:
            self.stdout.write(self.style.WARNING("No NestedTerritory nodes found. Skipping Step 2."))
            self.stdout.write(self.style.SUCCESS("\nProcess Finished! Client counts are now up-to-date."))
            return

        max_level = max_level_obj.level
        for level in range(max_level, -1, -1):
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE organization_nestedterritory AS parent
                    SET client_count = COALESCE((SELECT SUM(child.client_count) 
                                        FROM organization_nestedterritory AS child 
                                        WHERE child.parent_id = parent.id), 0)
                    WHERE parent.level = %s
                    AND parent.type != %s; -- Exclude ADDRESS type nodes
                """, [level, NestedTerritory.TerritoryType.ADDRESS])
            if verbose:
                self.stdout.write(f"  -> Processed nodes at level {level}.")

        self.stdout.write(self.style.SUCCESS("Step 2 Complete: All parent counts rolled up."))
        self.stdout.write(self.style.SUCCESS("\nProcess Finished! Client counts are now up-to-date."))
