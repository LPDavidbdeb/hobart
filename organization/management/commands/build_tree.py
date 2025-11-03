# In organization/management/commands/build_tree.py

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection

from organization.models import NestedTerritory
from organization.tree_definitions import (
    LEVEL_DEFINITIONS, TREE_COMPOSITIONS, BASE_GEODATA_PATH
)


class Command(BaseCommand):
    help = "Builds one or all complete territory trees from compositions."

    # ... (add_arguments method is unchanged) ...
    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            '--tree-name',
            type=str,
            choices=TREE_COMPOSITIONS.keys(),
            help='The name of a single tree composition to build.'
        )
        group.add_argument(
            '--all',
            action='store_true',
            help='Build ALL tree compositions defined in TREE_COMPOSITIONS.'
        )

        parser.add_argument(
            '--truncate',
            action='store_true',
            help='Truncate the NestedTerritory table and reset the primary key before building.',
        )

    # ... (handle method is unchanged) ...
    def handle(self, *args, **options):
        build_all = options['all']
        truncate = options['truncate']
        tree_name_single = options['tree_name']

        if truncate:
            self.stdout.write(self.style.WARNING(f"--- ⚠️ TRUNCATING TABLE: {NestedTerritory._meta.db_table} ---"))
            self.stdout.write(self.style.WARNING("  -> Resetting primary key sequence..."))

            with connection.cursor() as cursor:
                cursor.execute(f'TRUNCATE TABLE "{NestedTerritory._meta.db_table}" RESTART IDENTITY CASCADE;')

            self.stdout.write(self.style.SUCCESS("  -> Table truncated and primary key reset."))

        if build_all:
            trees_to_build = list(TREE_COMPOSITIONS.keys())
            self.stdout.write(self.style.SUCCESS(f"\n--- 🚀 Starting build for ALL {len(trees_to_build)} trees ---"))
        else:
            trees_to_build = [tree_name_single]
            self.stdout.write(self.style.SUCCESS(f"\n--- 🚀 Starting build for '{tree_name_single}' tree ---"))

        for tree_name in trees_to_build:
            with transaction.atomic():
                self._build_single_tree(tree_name)

        # --- Post-Build Stages (Unchanged) ---
        self.stdout.write(self.style.WARNING(f"\n--- Running Post-Build Stages (on all trees) ---"))
        self.stdout.write(self.style.NOTICE("    -> Stage 2: Validating tree integrity..."))
        call_command('verify_parent_containment')

        self.stdout.write(self.style.NOTICE("    -> Stage 3: Associating addresses and clients..."))
        call_command('place_addresses_in_tree')
        call_command('update_client_counts')

        self.stdout.write(self.style.SUCCESS(f"✅ Post-build stages complete."))
        self.stdout.write(self.style.SUCCESS(f"\n--- 🎉 All requested tree pipelines finished successfully ---"))

    # --- THIS IS THE MODIFIED METHOD ---
    def _build_single_tree(self, tree_name):
        """
        Helper method to build one complete tree composition.
        This method now handles its own MPTT rebuild.
        """
        self.stdout.write(self.style.WARNING(f"\n--- Building tree: '{tree_name}' ---"))

        try:
            level_keys_to_build = TREE_COMPOSITIONS[tree_name]
        except KeyError:
            raise CommandError(f"Tree composition '{tree_name}' not found.")

        self.stdout.write(f"  -> Building {len(level_keys_to_build)} territory levels...")

        self.stdout.write(self.style.NOTICE("    -> Disabling MPTT updates for bulk import..."))
        NestedTerritory.objects.disable_mptt_updates()

        # --- Import Loop (Unchanged) ---
        for level_key in level_keys_to_build:
            try:
                level_config = LEVEL_DEFINITIONS[level_key].copy()
            except KeyError:
                raise CommandError(f"Level '{level_key}' not defined in LEVEL_DEFINITIONS.")

            log_name = level_config.get('log_name', level_key)
            self.stdout.write(f"\n    --- Importing level: {log_name} ---")

            level_dir = BASE_GEODATA_PATH / level_key
            if not level_dir.exists():
                raise CommandError(f"Directory not found: {level_dir}")

            shapefiles = list(level_dir.glob('*.shp'))
            if len(shapefiles) == 0:
                raise CommandError(f"No .shp file found in {level_dir}")

            shapefile_path = shapefiles[0]
            self.stdout.write(f"    Found shapefile: {shapefile_path}")

            level_config['shapefile_path'] = str(shapefile_path)
            level_config['tree_name'] = tree_name

            call_command('import_tree_level', **level_config)

        self.stdout.write(self.style.SUCCESS(f"✅ Tree structure for '{tree_name}' built."))

        # -------------------------------------------------
        # --- THIS IS THE NEW, CONDITIONAL FIX ---
        # -------------------------------------------------
        # Before we rebuild, check if we need to fix the parents.
        if tree_name == 'statistical':
            self.stdout.write(self.style.WARNING(f"    -> Running 'fix_statistical_tree' for '{tree_name}'..."))
            try:
                call_command('fix_statistical_tree')
                self.stdout.write(self.style.SUCCESS(f"    -> Parent hierarchy for '{tree_name}' is now correct."))
            except Exception as e:
                raise CommandError(f"Failed to fix statistical tree. Did you create the command? Error: {e}")
        # -------------------------------------------------
        # --- END FIX ---
        # -------------------------------------------------

        self.stdout.write(
            self.style.NOTICE(f"    -> Rebuilding MPTT tree... (Processing '{tree_name}')"))

        # This will now be fast and low-memory because the tree is correctly parented.
        NestedTerritory.objects.rebuild()

        self.stdout.write(self.style.SUCCESS(f"    -> MPTT tree rebuilt."))