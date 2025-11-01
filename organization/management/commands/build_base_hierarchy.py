import time
import unicodedata
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon

from organization.models import NestedTerritory


class Command(BaseCommand):
    help = 'Builds a named base hierarchical tree (Country, Province, Region) from shapefiles.'

    def add_arguments(self, parser):
        parser.add_argument('province_shapefile', type=str, help='Path to the Statistics Canada province .shp file.')
        parser.add_argument('region_shapefile', type=str, help='Path to the Statistics Canada FED .shp file.')

        # Argument to specify the name of the tree being built
        parser.add_argument('--tree-name', required=True, type=str, help='A unique name for the hierarchy being built (e.g., \'Electoral\', \'Administrative\').')

        # Arguments for Province field names
        parser.add_argument('--prov-name-field', default='PRNOM', help='Shapefile field for the province name.')
        parser.add_argument('--prov-code-field', default='PRIDU', help='Shapefile field for the unique province ID.')

        # Arguments for Region (FED) field names
        parser.add_argument('--region-name-field', default='CÉFNOM', help='Shapefile field for the FED name.')
        parser.add_argument('--region-code-field', default='CÉFIDU', help='Shapefile field for the unique FED ID.')
        parser.add_argument('--region-parent-field', default='PRIDU', help='Shapefile field for linking FED to province.')

    def _ensure_multipolygon_4326(self, gdal_geom):
        if gdal_geom.srid != 4326:
            gdal_geom.transform(4326)
        geos_geom = GEOSGeometry(gdal_geom.wkt, srid=4326)
        if geos_geom.geom_type == 'Polygon':
            return MultiPolygon(geos_geom)
        if geos_geom.geom_type == 'MultiPolygon':
            return geos_geom
        raise TypeError(f"Unsupported geometry type: {geos_geom.geom_type}")

    def handle(self, *args, **options):
        tree_name = options['tree_name']
        start_time = time.time()

        self.stdout.write(self.style.WARNING(
            f"This is a destructive operation for the '{tree_name}' tree. It will wipe and rebuild the Country, Province, and Region levels for this tree only."))
        if input("Are you sure you want to continue? (y/n): ").lower() != 'y':
            self.stdout.write(self.style.ERROR("Operation cancelled."))
            return

        # Step 1: Clear old data for the specified tree
        self.stdout.write(self.style.WARNING(f"Step 1/2: Clearing old territory data for tree: '{tree_name}'..."))
        with transaction.atomic():
            NestedTerritory.objects.filter(tree_name=tree_name).delete()
        self.stdout.write(self.style.SUCCESS("  -> Complete."))

        # Step 2: Load Provinces and Regions
        self.stdout.write(self.style.SUCCESS("Step 2/2: Loading Provinces and Regions from shapefiles..."))
        with transaction.atomic():
            self._load_provinces_and_regions(options)
        self.stdout.write(self.style.SUCCESS("  -> Complete."))

        self.stdout.write(self.style.NOTICE("Rebuilding MPTT tree for consistency..."))
        NestedTerritory.objects.rebuild()
        self.stdout.write(self.style.SUCCESS("  -> Tree rebuilt."))

        end_time = time.time()
        self.stdout.write(self.style.SUCCESS(f"\nBase hierarchy for '{tree_name}' built in {end_time - start_time:.2f} seconds!"))

    def _load_provinces_and_regions(self, options):
        tree_name = options['tree_name']
        
        # Create the root node for this specific tree
        root_node = NestedTerritory.objects.create(name='Canada', type=NestedTerritory.TerritoryType.COUNTRY, tree_name=tree_name)

        # --- PROVINCES ---
        self.stdout.write("  -> Loading Provinces...")
        prov_ds = DataSource(options['province_shapefile'])
        prov_features = prov_ds[0]

        prov_nodes_to_create = []
        for feature in prov_features:
            try:
                prov_nodes_to_create.append(
                    NestedTerritory(
                        name=feature.get(options['prov_name_field']),
                        type=NestedTerritory.TerritoryType.PROVINCE,
                        parent=root_node,
                        boundary=self._ensure_multipolygon_4326(feature.geom),
                        code=feature.get(options['prov_code_field']),
                        tree_name=tree_name # Assign tree name
                    )
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"    Skipping province due to error: {e}"))

        NestedTerritory.objects.bulk_create(prov_nodes_to_create)
        self.stdout.write(f"  -> Created {len(prov_nodes_to_create)} province nodes.")

        # Create a mapping of {PRIDU: province_object} for the current tree
        province_map = {p.code: p for p in NestedTerritory.objects.filter(type=NestedTerritory.TerritoryType.PROVINCE, tree_name=tree_name)}

        # --- REGIONS (FEDs) ---
        self.stdout.write("  -> Loading Regions (FEDs)...")
        region_ds = DataSource(options['region_shapefile'])
        region_features = region_ds[0]

        region_nodes_to_create = []
        for feature in region_features:
            try:
                parent_pridu = feature.get(options['region_parent_field'])
                parent = province_map.get(parent_pridu)

                if parent:
                    region_nodes_to_create.append(
                        NestedTerritory(
                            name=feature.get(options['region_name_field']),
                            type=NestedTerritory.TerritoryType.REGION,
                            parent=parent,
                            boundary=self._ensure_multipolygon_4326(feature.geom),
                            code=feature.get(options['region_code_field']),
                            tree_name=tree_name # Assign tree name
                        )
                    )
                else:
                    self.stdout.write(self.style.WARNING(
                        f"    Skipping region '{feature.get(options['region_name_field'])}': Could not find parent province for ID {parent_pridu}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"    Skipping region due to error: {e}"))

        NestedTerritory.objects.bulk_create(region_nodes_to_create)
        self.stdout.write(f"  -> Created {len(region_nodes_to_create)} region nodes.")
