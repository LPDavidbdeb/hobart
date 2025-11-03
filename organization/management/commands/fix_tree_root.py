# In organization/management/commands/fix_tree_root.py

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from organization.models import NestedTerritory
import time


class Command(BaseCommand):
    help = ("Fixes a tree that was built with multiple root nodes (e.g., provinces) "
            "by adding a single 'Canada' root node above them.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--tree-name',
            required=True,
            type=str,
            help='The name of the tree to fix (e.g., \'statistical\', \'electoral\').'
        )
        parser.add_argument(
            '--root-name',
            type=str,
            default='Canada',
            help='The name for the new root node.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tree_name = options['tree_name']
        root_name = options['root_name']
        self.stdout.write(self.style.NOTICE(f"--- [START] Fixing root nodes for tree: '{tree_name}' ---"))

        # Step 1: Find all current root nodes for this tree (nodes with no parent)
        self.stdout.write(f"[1/5] Querying for existing root nodes (parent=NULL) for tree_name='{tree_name}'...")
        current_roots = NestedTerritory.objects.filter(
            tree_name=tree_name,
            parent__isnull=True
        )

        root_count = current_roots.count()

        if root_count == 0:
            self.stdout.write(self.style.WARNING(
                f"  -> Found 0 root nodes. No territories seem to exist for tree '{tree_name}'. Nothing to do."))
            self.stdout.write(self.style.NOTICE("--- [END] ---"))
            return

        if root_count == 1:
            self.stdout.write(self.style.SUCCESS(
                f"  -> Found 1 root node. The tree '{tree_name}' already has a single root. Nothing to do."))
            self.stdout.write(self.style.NOTICE("--- [END] ---"))
            return

        self.stdout.write(self.style.SUCCESS(f"  -> Found {root_count} root nodes (Provinces/Territories)."))

        # Step 2: Create the new, single "Canada" root node
        self.stdout.write(f"[2/5] Creating new '{root_name}' root node...")
        try:
            new_root = NestedTerritory.objects.create(
                name=root_name,
                type=NestedTerritory.TerritoryType.COUNTRY,
                tree_name=tree_name
                # Note: parent is NULL by default, making this a root
            )
            self.stdout.write(self.style.SUCCESS(
                f"  -> Created '{new_root.name}' (ID: {new_root.id}, lft: {new_root.lft}, rgt: {new_root.rgt}, level: {new_root.level})."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> FAILED to create new root node: {e}"))
            self.stdout.write(self.style.ERROR("  -> Aborting operation."))
            self.stdout.write(self.style.NOTICE("--- [FAIL] ---"))
            return

        # Step 3: Update all old roots to be children of the new root
        self.stdout.write(f"[3/5] Assigning {root_count} nodes as children of '{new_root.name}' (ID: {new_root.id})...")
        try:
            # This is the "magic" step. We just update the parent field.
            # MPTT fields are NOT updated yet, which is fine.
            updated_count = current_roots.update(parent=new_root)
            self.stdout.write(
                self.style.SUCCESS(f"  -> Database UPDATE complete. Parent field set for {updated_count} nodes."))
            if updated_count != root_count:
                self.stdout.write(self.style.WARNING(
                    f"  -> WARNING: Expected to update {root_count} nodes, but updated {updated_count}."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> FAILED to update parent fields: {e}"))
            self.stdout.write(self.style.ERROR("  -> Aborting operation."))
            self.stdout.write(self.style.NOTICE("--- [FAIL] ---"))
            return

        # Step 4: Rebuild the MPTT tree
        self.stdout.write(f"[4/5] Rebuilding MPTT tree for ALL nodes...")
        self.stdout.write(self.style.NOTICE("  -> Disabling MPTT updates for safety..."))
        try:
            NestedTerritory.objects.disable_mptt_updates()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  -> Could not disable MPTT updates (this is OK): {e}"))

        self.stdout.write(
            self.style.NOTICE("  -> Calling NestedTerritory.objects.rebuild()... (This may take a moment)"))
        start_time = time.time()
        try:
            NestedTerritory.objects.rebuild()
            end_time = time.time()
            self.stdout.write(self.style.SUCCESS(f"  -> Rebuild complete in {end_time - start_time:.2f} seconds."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  -> FATAL: MPTT rebuild FAILED: {e}"))
            self.stdout.write(self.style.ERROR(
                "  -> The tree is now in a broken state. You may need to restore from backup or truncate and rebuild."))
            self.stdout.write(self.style.NOTICE("--- [FAIL] ---"))
            return
        finally:
            self.stdout.write(self.style.NOTICE("  -> Re-enabling MPTT updates..."))
            NestedTerritory.objects.enable_mptt_updates()

        # Step 5: Verify the new structure
        self.stdout.write(f"[5/5] Verifying final tree structure...")
        final_root_count = NestedTerritory.objects.filter(tree_name=tree_name, parent__isnull=True).count()
        new_root_obj = NestedTerritory.objects.get(pk=new_root.pk)

        self.stdout.write(f"  -> Final root node count for '{tree_name}': {final_root_count}")
        self.stdout.write(f"  -> New root node '{new_root_obj.name}' (ID: {new_root_obj.id}) final MPTT values:")
        self.stdout.write(f"     lft: {new_root_obj.lft}")
        self.stdout.write(f"     rgt: {new_root_obj.rgt}")
        self.stdout.write(f"     level: {new_root_obj.level}")
        self.stdout.write(f"     child count: {new_root_obj.get_children().count()}")

        if final_root_count == 1 and new_root_obj.get_children().count() == updated_count:
            self.stdout.write(
                self.style.SUCCESS(f"  -> VERIFIED: Tree for '{tree_name}' successfully unified under a single root!"))
        else:
            self.stdout.write(self.style.ERROR(f"  -> FAILED VERIFICATION: Expected 1 root, found {final_root_count}."))

        self.stdout.write(self.style.NOTICE(f"--- [SUCCESS] Operation complete for tree: '{tree_name}' ---"))