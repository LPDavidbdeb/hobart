from django.core.management.base import BaseCommand
from address.models import Address
from organization.models import NestedTerritory

class Command(BaseCommand):
    help = 'Associates addresses with their corresponding territory leaves and ancestors using a high-performance, territory-first approach.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tree-name',
            type=str,
            help='The name of the territory tree to process.',
            default='Default'
        )
        parser.add_argument(
            '--leaf-type',
            type=str,
            help="The 'type' of the leaf nodes to link from (e.g., 'CITY', 'FSA').",
            required=True
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            help='The number of links to create before committing to the database.',
            default=10000
        )


    def handle(self, *args, **options):
        tree_name = options['tree_name']
        leaf_type = options['leaf_type']
        batch_size = options['batch_size']

        self.stdout.write(self.style.SUCCESS(f"Starting association for tree: '{tree_name}' using leaf type: '{leaf_type}'"))

        # Get the 'through' model that links Address and NestedTerritory
        AddressTerritoryLink = Address.territories.through

        # 1. Clear ALL old associations for this tree in ONE query.
        self.stdout.write(f"  -> Clearing old links for '{tree_name}'...")
        old_links = AddressTerritoryLink.objects.filter(nestedterritory__tree_name=tree_name)
        count, _ = old_links.delete()
        self.stdout.write(f"  -> Cleared {count} old links.")

        # 2. Get all leaf nodes for this tree of the specified type
        leaf_nodes = NestedTerritory.objects.filter(
            tree_name=tree_name, 
            type=leaf_type
        )
        
        self.stdout.write(f"Found {leaf_nodes.count()} leaf nodes to process.")
        links_to_create = []

        # 3. Loop through each LEAF NODE
        for i, leaf_node in enumerate(leaf_nodes):
            
            # 4. Get the full branch for this leaf ONCE
            ancestor_node_ids = list(
                leaf_node.get_ancestors(include_self=True).values_list('id', flat=True)
            )
            
            # 5. Find all addresses that match this leaf in ONE query
            # This logic needs to be adapted based on the leaf_type
            if leaf_type == 'CITY':
                matching_addresses_ids = list(
                    Address.objects.filter(city__iexact=leaf_node.name).values_list('id', flat=True)
                )
            elif leaf_type == 'FSA':
                matching_addresses_ids = list(
                    Address.objects.filter(postal_code__startswith=leaf_node.name).values_list('id', flat=True)
                )
            else:
                self.stdout.write(self.style.WARNING(f"  -> Skipping leaf type '{leaf_type}'. No matching logic defined."))
                continue

            if not matching_addresses_ids:
                continue
            
            self.stdout.write(f"  ({i+1}/{leaf_nodes.count()}) Found {len(matching_addresses_ids)} addresses for leaf '{leaf_node.name}'. Preparing {len(matching_addresses_ids) * len(ancestor_node_ids)} links.")

            # 6. Prepare the links for bulk creation
            for address_id in matching_addresses_ids:
                for territory_id in ancestor_node_ids:
                    links_to_create.append(
                        AddressTerritoryLink(
                            address_id=address_id,
                            nestedterritory_id=territory_id
                        )
                    )

            # 7. Periodically flush the bulk create for memory efficiency
            if len(links_to_create) >= batch_size:
                AddressTerritoryLink.objects.bulk_create(links_to_create, ignore_conflicts=True)
                self.stdout.write(f"    ... committed {len(links_to_create)} links to the database.")
                links_to_create = []

        # 8. Add any remaining links
        if links_to_create:
            AddressTerritoryLink.objects.bulk_create(links_to_create, ignore_conflicts=True)
            self.stdout.write(f"  -> Committed final {len(links_to_create)} links.")

        self.stdout.write(self.style.SUCCESS(f"Successfully associated addresses for tree '{tree_name}'."))
