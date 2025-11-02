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
        # ... (this section is unchanged)
        parser.add_argument('--shapefile_path', type=str, required=True)
        parser.add_argument('--level_name', type=str, required=True)
        parser.add_argument('--name_field', type=str, required=True)
        parser.add_argument('--code_field', type=str, required=True)
        parser.add_argument('--parent_code_field', type=str, default=None)

    @transaction.atomic
    def handle(self, *args, **options):
        # ... (options setup is unchanged)
        shapefile_path = options['shapefile_path']
        level_name = options['level_name']
        name_field = options['name_field']
        code_field = options['code_field']
        parent_code_field = options['parent_code_field']

        self.stdout.write(f"Importing level '{level_name}' from {shapefile_path}...")
        created_count = 0
        updated_count = 0

        try:
            with fiona.open(shapefile_path, 'r') as shapefile:
                # ... (CRS detection logic is unchanged)
                source_crs = shapefile.crs
                if not source_crs:
                    raise CommandError("Shapefile is missing CRS (projection) information.")

                source_srid = source_crs.get('init')
                if not source_srid or 'epsg' not in source_srid.lower():
                    try:
                        source_srid_num_str = fiona.crs.to_string(source_crs).split(':')[-1]
                        if not source_srid_num_str.isdigit():
                            raise Exception("Could not parse SRID")
                    except Exception:
                        raise CommandError(f"Could not parse SRID from CRS: {source_crs}")
                else:
                    source_srid_num_str = source_srid.split(':')[-1]

                # --- THIS IS THE FIX ---
                # Convert the SRID string to an integer
                try:
                    source_srid_num = int(source_srid_num_str)
                except ValueError:
                    raise CommandError(f"Could not convert SRID '{source_srid_num_str}' to an integer.")

                target_srid_num = 4326  # Use an integer here as well
                # --- END FIX ---

                for feature in shapefile:
                    props = feature['properties']

                    try:
                        shapely_geom = shape(feature['geometry'])
                        geom_wkt = shapely_geom.wkt

                        geom_obj = GEOSGeometry(geom_wkt)

                        # Set the SRID *using the integer*
                        geom_obj.srid = source_srid_num

                    except shapely.errors.ShapelyError as e:
                        self.stdout.write(
                            self.style.WARNING(f"Skipping {props[name_field]}: Invalid geometry. Error: {e}"))
                        continue
                    except (AttributeError, TypeError, ValueError) as e:
                        self.stdout.write(
                            self.style.WARNING(f"Skipping {props[name_field]}: No geometry found. Error: {e}"))
                        continue

                    if source_srid_num != target_srid_num:
                        geom_obj.transform(target_srid_num)

                    # ... (rest of the file is unchanged)
                    if geom_obj.geom_type == 'Polygon':
                        geom_obj = MultiPolygon([geom_obj])
                    elif geom_obj.geom_type != 'MultiPolygon':
                        self.stdout.write(self.style.WARNING(
                            f"Skipping {props[name_field]}: Invalid geometry type {geom_obj.geom_type}"))
                        continue

                    parent = None
                    if parent_code_field:
                        parent_code = props.get(parent_code_field)
                        if not parent_code:
                            raise CommandError(
                                f"Feature {props[name_field]} missing parent code in field {parent_code_field}")

                        try:
                            parent = NestedTerritory.objects.get(code=parent_code)
                        except NestedTerritory.DoesNotExist:
                            self.stdout.write(self.style.WARNING(
                                f"Skipping {props[name_field]}: Parent with code {parent_code} not found."))
                            continue

                    territory, created = NestedTerritory.objects.update_or_create(
                        code=props[code_field],
                        defaults={
                            'name': props[name_field],
                            'level_name': level_name,
                            'parent': parent,
                            'boundary': geom_obj,
                        }
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

            self.stdout.write(self.style.SUCCESS(
                f"Successfully imported '{level_name}': {created_count} created, {updated_count} updated."))

        except fiona.errors.DriverError as e:
            raise CommandError(
                f"Could not open shapefile at {shapefile_path}. Do you have all files (.shx, .dbf, .prj)? Error: {e}")
        except KeyError as e:
            raise CommandError(f"Missing field in shapefile: {e}. Check your config's name_field/code_field.")