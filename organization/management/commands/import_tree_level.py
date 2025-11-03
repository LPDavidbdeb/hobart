# In organization/management/commands/import_tree_level.py

import fiona
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from organization.models import NestedTerritory
from shapely.geometry import shape
import shapely.errors


class Command(BaseCommand):
    help = 'Imports a single level of a territory tree from a shapefile.'

    def add_arguments(self, parser):
        parser.add_argument('--shapefile_path', type=str, required=True)
        parser.add_argument('--log_name', type=str, required=True)
        parser.add_argument('--territory_type', type=str, required=True)
        parser.add_argument('--name_field', type=str, required=True)
        parser.add_argument('--code_field', type=str, required=True)
        parser.add_argument('--parent_code_field', type=str, default=None)
        parser.add_argument('--parent_type', type=str, default=None)
        parser.add_argument('--tree_name', type=str, required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        shapefile_path = options['shapefile_path']
        log_name = options['log_name']
        territory_type = options['territory_type']
        tree_name = options['tree_name']
        name_field = options['name_field']
        code_field = options['code_field']
        parent_code_field = options['parent_code_field']
        parent_type = options['parent_type']

        self.stdout.write(f"Importing level '{log_name}' for tree '{tree_name}'...")
        nodes_to_create = []  # <-- List to hold new objects
        skipped_count = 0

        try:
            with fiona.open(shapefile_path, 'r') as shapefile:
                # --- VALIDATION BLOCK (Unchanged) ---
                available_fields = list(shapefile.schema['properties'].keys())
                required_fields_to_check = {'name_field': name_field, 'code_field': code_field}
                if parent_code_field:
                    required_fields_to_check['parent_code_field'] = parent_code_field
                for config_key, field_name_to_find in required_fields_to_check.items():
                    if field_name_to_find not in available_fields:
                        raise CommandError(
                            f"\n\nConfiguration Mismatch!\n"
                            f"Your config specifies '{config_key}: \"{field_name_to_find}\"', but that field was not found in the shapefile.\n\n"
                            f"FILE: {shapefile_path}\n"
                            f"AVAILABLE FIELDS: {available_fields}\n"
                        )
                # --- END VALIDATION ---

                # --- CRS detection (Unchanged) ---
                source_crs = shapefile.crs
                if not source_crs: raise CommandError("Shapefile is missing CRS (projection) information.")
                source_srid = source_crs.get('init')
                if not source_srid or 'epsg' not in source_srid.lower():
                    try:
                        source_srid_num_str = fiona.crs.to_string(source_crs).split(':')[-1]
                    except Exception:
                        raise CommandError(f"Could not parse SRID from CRS: {source_crs}")
                else:
                    source_srid_num_str = source_srid.split(':')[-1]
                try:
                    source_srid_num = int(source_srid_num_str)
                except ValueError:
                    raise CommandError(f"Could not convert SRID '{source_srid_num_str}' to an integer.")
                target_srid_num = 4326
                # --- End CRS ---

                # -------------------------------------------------
                # --- OPTIMIZATION: 1. FETCH PARENTS ---
                # -------------------------------------------------
                parent_map = {}
                if parent_code_field and parent_type:
                    self.stdout.write(self.style.NOTICE("  -> Fetching parent nodes into memory..."))
                    parents = NestedTerritory.objects.filter(
                        type=parent_type,
                        tree_name=tree_name
                    )
                    # Create a map of {parent_code: parent_object}
                    parent_map = {p.code: p for p in parents}
                    self.stdout.write(self.style.NOTICE(f"  -> Found {len(parent_map)} parents."))
                # -------------------------------------------------

                unique_check = set()  # Set to check for duplicates *within the file*

                for feature in shapefile:
                    props = feature['properties']

                    try:
                        shapely_geom = shape(feature['geometry'])
                        geom_wkt = shapely_geom.wkt
                        geom_obj = GEOSGeometry(geom_wkt)
                        geom_obj.srid = source_srid_num
                    except (shapely.errors.ShapelyError, AttributeError, TypeError, ValueError):
                        skipped_count += 1
                        continue

                    if source_srid_num != target_srid_num:
                        geom_obj.transform(target_srid_num)

                    if geom_obj.geom_type == 'Polygon':
                        geom_obj = MultiPolygon([geom_obj])
                    elif geom_obj.geom_type != 'MultiPolygon':
                        skipped_count += 1
                        continue

                    # --- OPTIMIZATION: 2. FIND PARENT FROM MEMORY ---
                    parent = None
                    if parent_code_field and parent_type:
                        parent_code = props.get(parent_code_field)
                        parent = parent_map.get(parent_code)  # <-- Fast lookup from map

                        if not parent:
                            # This skips items without a valid parent
                            skipped_count += 1
                            continue

                    # --- Create object in memory ---
                    name = props[name_field]
                    code = props[code_field]

                    # Check for duplicates *within this file* to prevent IntegrityError
                    unique_key = (name, parent.id if parent else None, territory_type, tree_name)
                    if unique_key in unique_check:
                        skipped_count += 1
                        continue
                    unique_check.add(unique_key)

                    # Create the object without saving it
                    node = NestedTerritory(
                        name=name,
                        code=code,
                        type=territory_type,
                        parent=parent,
                        tree_name=tree_name,
                        boundary=geom_obj,
                    )
                    nodes_to_create.append(node)  # Add to our big list

                # -------------------------------------------------
                # --- OPTIMIZATION: 3. BULK INSERT ---
                # -------------------------------------------------
                if nodes_to_create:
                    self.stdout.write(self.style.NOTICE(f"  -> Inserting {len(nodes_to_create)} new nodes in bulk..."))
                    # We ignore conflicts in case a --clear failed and some nodes exist
                    NestedTerritory.objects.bulk_create(nodes_to_create, ignore_conflicts=True)
                # -------------------------------------------------

            self.stdout.write(self.style.SUCCESS(
                f"Successfully processed import for '{log_name}': {len(nodes_to_create)} created, {skipped_count} skipped."))

        except fiona.errors.DriverError as e:
            raise CommandError(
                f"Could not open shapefile at {shapefile_path}. Do you have all files (.shx, .dbf, .prj)? Error: {e}")