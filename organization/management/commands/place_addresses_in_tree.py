import time
from django.core.management.base import BaseCommand
from django.db import transaction

from address.models import Address
from organization.models import NestedTerritory, AddressTerritoryLink


class Command(BaseCommand):
    help = 'Places addresses into the leaf nodes of a specified territory tree using spatial queries.'

    def add_arguments(self, parser):
        parser.add_argument('tree_name', type=str, help='The name of the tree to place addresses in (e.g., \'Electoral\').')

    def handle(self, *args, **options):
        tree_name = options['tree_name']
        start_time = time.time()

        self.stdout.write(self.style.NOTICE(f"Starting address placement for the '{tree_name}' tree..."))

        # --- Step 1: Clear any existing links for this tree to ensure a clean run ---
        self.stdout.write(self.style.WARNING(f"  -> Deleting existing links for the '{tree_name}' tree..."))
        with transaction.atomic():
            links_deleted, _ = AddressTerritoryLink.objects.filter(tree_name=tree_name).delete()
        self.stdout.write(self.style.SUCCESS(f"  -> Deleted {links_deleted} old links."))

        # --- Step 2: Get all leaf nodes for the specified tree ---
        try:
            root_node = NestedTerritory.objects.get(tree_name=tree_name, level=0)
            # is_leaf=True is an efficient MPTT query
            leaf_nodes = root_node.get_descendants().filter(is_leaf=True, boundary__isnull=False)
            leaf_node_count = leaf_nodes.count()
            if leaf_node_count == 0:
                self.stdout.write(self.style.ERROR(f"No leaf nodes with boundaries found for tree '{tree_name}'. Cannot place addresses."))
                return
        except NestedTerritory.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"No root node found for tree '{tree_name}'. Please build the hierarchy first."))
            return

        self.stdout.write(f"  -> Found {leaf_node_count} leaf nodes with boundaries to process.")

        # --- Step 3: Iterate through leaves and place addresses ---
        total_links_created = 0
        processed_leaves = 0

        for leaf in leaf_nodes.iterator():
            with transaction.atomic():
                # Find all addresses within this leaf's boundary that are not yet linked to this tree
                addresses_in_leaf = Address.objects.filter(
                    location__isnull=False,
                    location__within=leaf.boundary
                )
                
                links_to_create = []
                for address in addresses_in_leaf:
                    links_to_create.append(
                        AddressTerritoryLink(
                            address=address,
                            territory=leaf,
                            tree_name=tree_name
                        )
                    )
                
                if links_to_create:
                    AddressTerritoryLink.objects.bulk_create(links_to_create, ignore_conflicts=True)
                    total_links_created += len(links_to_create)
            
            processed_leaves += 1
            if processed_leaves % 100 == 0:
                self.stdout.write(f"    ... processed {processed_leaves}/{leaf_node_count} leaf nodes. Total links so far: {total_links_created}")


        end_time = time.time()
        self.stdout.write(self.style.SUCCESS(f"\nAddress placement finished in {end_time - start_time:.2f} seconds!"))
        self.stdout.write(self.style.SUCCESS(f"Created {total_links_created} new address-territory links for the '{tree_name}' tree."))
