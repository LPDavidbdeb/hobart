# In organization/management/commands/build_tree.py

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from organization.tree_definitions import (
    LEVEL_DEFINITIONS, TREE_COMPOSITIONS, BASE_GEODATA_PATH
)


class Command(BaseCommand):
    help = "Builds a complete territory tree from a named composition."

    def add_arguments(self, parser):
        parser.add_argument(
            '--tree-name',
            type=str,
            required=True,
            choices=TREE_COMPOSITIONS.keys(),
            help='The name of the tree composition to build.'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete all existing territories before building.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tree_name = options['tree_name']

        self.stdout.write(self.style.SUCCESS(f"--- 🚀 Starting build for '{tree_name}' tree ---"))

        if options['clear']:
            self.stdout.write(self.style.WARNING("Clearing all existing territories..."))
            from organization.models import NestedTerritory
            NestedTerritory.objects.all().delete()
            self.stdout.write(self.style.WARNING("All territories cleared."))

        # --- STAGE 1: Build the tree structure ---
        try:
            level_keys_to_build = TREE_COMPOSITIONS[tree_name]
        except KeyError:
            raise CommandError(f"Tree composition '{tree_name}' not found.")

        self.stdout.write(self.style.WARNING(f"\nStage 1: Building {len(level_keys_to_build)} territory levels..."))

        for level_key in level_keys_to_build:
            try:
                level_config = LEVEL_DEFINITIONS[level_key].copy()
            except KeyError:
                raise CommandError(f"Level '{level_key}' not defined in LEVEL_DEFINITIONS.")

            self.stdout.write(f"\n--- Importing level: {level_config['level_name']} ---")

            level_dir = BASE_GEODATA_PATH / level_key
            if not level_dir.exists():
                raise CommandError(f"Directory not found: {level_dir}")

            shapefiles = list(level_dir.glob('*.shp'))
            if len(shapefiles) == 0:
                raise CommandError(f"No .shp file found in {level_dir}")
            if len(shapefiles) > 1:
                self.stdout.write(self.style.WARNING(f"Multiple .shp files found, using first one: {shapefiles[0]}"))

            shapefile_path = shapefiles[0]
            self.stdout.write(f"Found shapefile: {shapefile_path}")

            level_config['shapefile_path'] = str(shapefile_path)

            call_command('import_tree_level', **level_config)

        self.stdout.write(self.style.SUCCESS("✅ Stage 1 Complete: Tree structure built."))

        # --- STAGE 2: Validate tree integrity ---
        self.stdout.write(self.style.WARNING("\nStage 2: Validating tree integrity..."))
        call_command('verify_parent_containment')
        self.stdout.write(self.style.SUCCESS("✅ Stage 2 Complete: Tree is valid."))

        # --- STAGE 3: Associate data with the tree ---
        self.stdout.write(self.style.WARNING("\nStage 3: Associating addresses and clients..."))
        call_command('place_addresses_in_tree')
        call_command('update_client_counts')
        self.stdout.write(self.style.SUCCESS("✅ Stage 3 Complete: Data associated."))

        self.stdout.write(self.style.SUCCESS(f"\n--- 🎉 Pipeline for '{tree_name}' Finished Successfully ---"))