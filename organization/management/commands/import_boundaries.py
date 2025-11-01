from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import MultiPolygon
from organization.models import NestedTerritory

# Maps a lowercase name from YOUR DATABASE to the expected lowercase name in the SHAPEFILE
DB_TO_SHAPEFILE_NAME_MAP = {
    'nouvelle-ecosse': 'nova scotia',
    'quebec': 'québec',
    # Add other mappings here if needed, e.g. 'prince edward island': 'prince edward i.'
}

class Command(BaseCommand):
    help = 'Imports province/state boundaries from the Natural Earth shapefile into the NestedTerritory model.'

    def add_arguments(self, parser):
        parser.add_argument(
            'shapefile',
            type=str,
            help='The absolute path to the .shp file for the states/provinces.',
        )

    def handle(self, *args, **options):
        shapefile_path = Path(options['shapefile'])

        if not shapefile_path.exists():
            self.stdout.write(self.style.ERROR(f'Shapefile not found at: {shapefile_path}'))
            return

        self.stdout.write('Loading shapefile features into memory...')
        ds = DataSource(shapefile_path)
        layer = ds[0]
        
        # Create a dictionary of all shapefile features for fast lookup
        shapefile_geoms = {}
        for feature in layer:
            name = feature.get('name')
            if name:
                shapefile_geoms[name.lower()] = feature.geom
        self.stdout.write(f'  -> Found {len(shapefile_geoms)} features in shapefile.')

        self.stdout.write('Matching and updating database territories...')
        
        # Get only PROVINCE nodes from the database
        db_provinces = NestedTerritory.objects.filter(type=NestedTerritory.TerritoryType.PROVINCE)
        
        updated_count = 0
        not_found_names = []

        for territory in db_provinces:
            db_name_lower = territory.name.lower()
            
            # Use the mapping to find the corresponding shapefile name, or use the db name if not in map
            shapefile_lookup_name = DB_TO_SHAPEFILE_NAME_MAP.get(db_name_lower, db_name_lower)
            
            geom = shapefile_geoms.get(shapefile_lookup_name)

            if geom:
                try:
                    if geom.geom_type == 'Polygon':
                        territory.boundary = MultiPolygon(geom.geos)
                    elif geom.geom_type == 'MultiPolygon':
                        territory.boundary = geom.geos
                    else:
                        self.stdout.write(self.style.WARNING(f"Skipping '{territory.name}' due to unexpected geometry type: {geom.geom_type}"))
                        continue

                    territory.save(update_fields=['boundary'])
                    updated_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  -> Error updating '{territory.name}': {e}"))
            else:
                not_found_names.append(territory.name)

        # --- Final Summary ---
        self.stdout.write("\n" + self.style.SUCCESS('Import Complete!'))
        self.stdout.write(f'- {updated_count} province territories in the database were updated with boundaries.')
        
        if not_found_names:
            self.stdout.write(self.style.WARNING(f'\n- {len(not_found_names)} provinces from your database were NOT found in the shapefile:'))
            for name in sorted(not_found_names):
                self.stdout.write(f'  - {name}')
        else:
            self.stdout.write(self.style.SUCCESS('\n- All province territories in your database were found and updated.'))

        self.stdout.write(self.style.NOTICE("\nNote: Country boundaries (e.g., for 'Canada') must be imported from a separate country-level (admin_0) shapefile."))
