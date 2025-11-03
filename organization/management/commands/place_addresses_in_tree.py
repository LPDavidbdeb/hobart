import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from address.models import Address
from organization.models import NestedTerritory
# We no longer import AddressTerritoryLink, as it doesn't exist.

class Command(BaseCommand):
    help = 'Places addresses into the leaf nodes of a specified territory tree using spatial queries.'

    def add_arguments(self, parser):
        parser.add_argument('tree_name', type=str,
                            help='The name of the tree to place addresses in (e.g., \'Electoral\').')

    def handle(self, *args, **options):
        tree_name = options['tree_name']
        start_time = time.time()

        self.stdout.write(self.style.NOTICE(f"Starting address placement for the '{tree_name}' tree..."))

        # --- Step 1: Get the M2M "through" model ---
        AddressTerritoryLink = Address.territories.through

        # --- Step 2: Clear any existing links for this tree to ensure a clean run ---
        self.stdout.write(self.style.WARNING(f"  -> Deleting existing links for the '{tree_name}' tree..."))

        with transaction.atomic():
            territory_ids = NestedTerritory.objects.filter(tree_name=tree_name).values_list('id', flat=True)
            links_deleted, _ = AddressTerritoryLink.objects.filter(
                nestedterritory_id__in=territory_ids
            ).delete()

        self.stdout.write(self.style.SUCCESS(f"  -> Deleted {links_deleted} old links."))

        # -------------------------------------------------
        # --- THIS IS THE FIX ---
        # -------------------------------------------------
        # We don't need to find a single root node.
        # We can just get *all* leaf nodes for the specified tree directly.
        self.stdout.write(f"  -> Finding all leaf nodes for tree '{tree_name}'...")
        try:
            # This is the new, correct query:
            leaf_nodes = NestedTerritory.objects.filter(
                tree_name=tree_name,
                rght=F('lft') + 1,
                boundary__isnull=False
            )
            leaf_node_count = leaf_nodes.count()

            if leaf_node_count == 0:
                self.stdout.write(self.style.ERROR(
                    f"No leaf nodes with boundaries found for tree '{tree_name}'. Cannot place addresses."))
                return
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"An unexpected error occurred while fetching leaf nodes: {e}"))
            return
        # -------------------------------------------------
        # --- END FIX ---
        # -------------------------------------------------

        self.stdout.write(f"  -> Found {leaf_node_count} leaf nodes with boundaries to process.")

        # --- Step 4: Iterate through leaves and bulk-create links ---
        total_links_created = 0
        processed_leaves = 0

        # .iterator() is essential for memory efficiency with many nodes
        for leaf in leaf_nodes.iterator():
            with transaction.atomic():
                addresses_in_leaf = Address.objects.filter(
                    location__isnull=False,
                    location__within=leaf.boundary
                ).only('id')

                links_to_create = []
                for address in addresses_in_leaf:
                    links_to_create.append(
                        AddressTerritoryLink(
                            address_id=address.id,
                            nestedterritory_id=leaf.id
                        )
                    )

                if links_to_create:
                    AddressTerritoryLink.objects.bulk_create(links_to_create, ignore_conflicts=True)
                    total_links_created += len(links_to_create)

            processed_leaves += 1
            if processed_leaves % 100 == 0:
                self.stdout.write(
                    f"    ... processed {processed_leaves}/{leaf_node_count} leaf nodes. Total links so far: {total_links_created}")

        end_time = time.time()
        self.stdout.write(self.style.SUCCESS(f"\nAddress placement finished in {end_time - start_time:.2f} seconds!"))
        self.stdout.write(self.style.SUCCESS(
            f"Created {total_links_created} new address-territory links for the '{tree_name}' tree."))
