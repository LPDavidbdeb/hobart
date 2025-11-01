from django.core.management.base import BaseCommand
from organization.models import NestedTerritory

class Command(BaseCommand):
    help = 'Debugs the root nodes of the NestedTerritory tree.'

    def handle(self, *args, **options):
        self.stdout.write("Querying for root nodes (level=0) in NestedTerritory...")

        # MPTT stores root nodes at level 0
        root_nodes = NestedTerritory.objects.filter(level=0)

        if not root_nodes.exists():
            self.stdout.write(self.style.ERROR("Error: No root nodes found! The tree was not created correctly."))
            # Let's check if there is any data at all
            total_nodes = NestedTerritory.objects.count()
            self.stdout.write(f"Total nodes in table: {total_nodes}")
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(root_nodes)} root node(s):"))
        for node in root_nodes:
            self.stdout.write(
                f"  - ID: {node.id}, "
                f"Name: '{node.name}', "
                f"Type: '{node.type}', "
                f"Level: {node.level}, "
                f"LFT: {node.lft}, "
                f"RGHT: {node.rght}"
            )
