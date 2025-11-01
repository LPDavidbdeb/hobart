import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from address.models import Address
from organization.models import NestedTerritory


class Command(BaseCommand):
    help = "Associates all addresses with their full ancestral branch in a specified MPTT tree."

    def add_arguments(self, parser):
        parser.add_argument(
            '--tree-name',
            type=str,
            required=True,
            help="The 'tree_name' of the hierarchy to associate (e.g., 'Administrative', 'Electoral')."
        )

    def handle(self, *args, **options):
        start_time = time.time()
        tree_name = options['tree_name']
        self.stdout.write(self.style.NOTICE(f"Starting association for tree: '{tree_name}'..."))

        # Get the 'through' model that links Address and NestedTerritory
        AddressTerritoryLink = Address.territories.through

        # 1. Clear ALL old associations for this tree in ONE query.
        self.stdout.write(f"  -> Clearing old links for '{tree_name}'...")
        old_links = AddressTerritoryLink.objects.filter(nestedterritory__tree_name=tree_name)
        count, _ = old_links.delete()
        self.stdout.write(f"  -> Cleared {count} old links.")

        # 2. Get all LEAF nodes for this tree (nodes with no children)
        # This is your corrected logic!
        leaf_nodes = NestedTerritory.objects.filter(
            tree_name=tree_name,
            children__isnull=True  # Finds all nodes that are leaves
        )

        leaf_node_count = leaf_nodes.count()
        if leaf_node_count == 0:
            self.stdout.write(self.style.WARNING(
                f"Found 0 leaf nodes in tree '{tree_name}'. Make sure you ran the loading script with the correct tree_name."))
            return

        self.stdout.write(f"Found {leaf_node_count} leaf nodes to process.")
        links_to_create = []
        total_links_created = 0

        # 3. Loop through each LEAF NODE (e.g., all 338 FEDs)
        for i, leaf_node in enumerate(leaf_nodes.iterator()):

            # 4. Get the full branch for this leaf ONCE
            ancestor_node_ids = list(
                leaf_node.get_ancestors(include_self=True).values_list('id', flat=True)
            )

            # 5. Find all addresses that are spatially contained within this leaf
            # This is the most important query.
            matching_addresses_ids = list(
                Address.objects.filter(
                    location__intersects=leaf_node.boundary
                ).values_list('id', flat=True)
            )

            if not matching_addresses_ids:
                continue

            # 6. Prepare the links for bulk creation
            # (e.g., 50 addresses * 3 ancestors = 150 links)
            for address_id in matching_addresses_ids:
                for territory_id in ancestor_node_ids:
                    links_to_create.append(
                        AddressTerritoryLink(
                            address_id=address_id,
                            nestedterritory_id=territory_id
                        )
                    )

            # 7. Periodically flush the bulk create for memory efficiency
            if len(links_to_create) > 5000 or (i + 1) == leaf_node_count:
                AddressTerritoryLink.objects.bulk_create(links_to_create, ignore_conflicts=True)
                total_links_created += len(links_to_create)
                self.stdout.write(
                    f"    ... processed node {i + 1}/{leaf_node_count} ('{leaf_node.name}'). Committed {len(links_to_create)} links.")
                links_to_create = []

        end_time = time.time()
        self.stdout.write(self.style.SUCCESS(
            f"\nSuccessfully created {total_links_created} links in {end_time - start_time:.2f} seconds for tree '{tree_name}'."))