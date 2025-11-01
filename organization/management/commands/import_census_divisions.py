import unicodedata
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import MultiPolygon
from organization.models import NestedTerritory

TERMS_TO_REMOVE = [
    'regional municipality of', 'regional district of', 'county of', 'municipal district of',
    'improvement district', 'regional district', 'municipal disctrict of', 'united counties of',
    'comtes unis de', 'municipalite regionale de comte', 'mrc de',
    'county', 'district', 'region', 'regional', 'municipality', 'municipal'
]

def clean_name(name):
    if not name:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', name.lower())
    normalized = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    for term in TERMS_TO_REMOVE:
        normalized = normalized.replace(term, '')
    normalized = re.sub(r'[\d\-/\.]+', '', normalized)
    return normalized.strip()

class Command(BaseCommand):
    help = 'Matches and imports Census Division boundaries for REGION territories.'

    def add_arguments(self, parser):
        parser.add_argument('shapefile', type=str, help='Path to the .shp file for census divisions.')
        parser.add_argument('--name-field', default='DRNOM', help='Shapefile field for the division name.')
        parser.add_argument('--code-field', default='DRIDU', help='Shapefile field for the unique division ID.')

    def handle(self, *args, **options):
        shapefile_path = Path(options['shapefile'])
        name_field = options['name_field']
        code_field = options['code_field']

        if not shapefile_path.exists():
            self.stdout.write(self.style.ERROR(f'Shapefile not found at: {shapefile_path}'))
            return

        self.stdout.write('Loading shapefile features into memory...')
        ds = DataSource(shapefile_path)
        layer = ds[0]
        shapefile_features = {clean_name(f.get(name_field)): {'geom': f.geom, 'code': f.get(code_field)} for f in layer if f.get(name_field)}
        self.stdout.write(f'  -> Found {len(shapefile_features)} features in shapefile.\n')

        # Target only unprocessed regions
        db_regions = NestedTerritory.objects.filter(
            type=NestedTerritory.TerritoryType.REGION,
            boundary_status=NestedTerritory.BoundaryStatus.UNPROCESSED
        )

        if not db_regions.exists():
            self.stdout.write(self.style.SUCCESS('No unprocessed REGION territories found. Nothing to do.'))
            return

        self.stdout.write(f'Found {db_regions.count()} unprocessed regions. Starting matching process...')
        
        updated_count = 0
        marked_for_scraping_count = 0

        for territory in db_regions:
            cleaned_db_name = clean_name(territory.name)
            match_geom = None
            match_code = None

            # Strategy 1: Exact match on cleaned name
            if cleaned_db_name in shapefile_features:
                match_geom = shapefile_features[cleaned_db_name]['geom']
                match_code = shapefile_features[cleaned_db_name]['code']
            else:
                # Strategy 2: Check if a unique shapefile name is contained within the DB name
                possible_matches = [shp_name for shp_name in shapefile_features if shp_name in cleaned_db_name]
                if len(possible_matches) == 1:
                    match_key = possible_matches[0]
                    match_geom = shapefile_features[match_key]['geom']
                    match_code = shapefile_features[match_key]['code']

            if match_geom and match_code:
                try:
                    if match_geom.geom_type == 'Polygon':
                        territory.boundary = MultiPolygon(match_geom.geos)
                    else:
                        territory.boundary = match_geom.geos
                    
                    territory.code = match_code
                    territory.boundary_status = NestedTerritory.BoundaryStatus.MATCHED
                    territory.save(update_fields=['boundary', 'code', 'boundary_status'])
                    updated_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  -> Error updating '{territory.name}': {e}"))
            else:
                # If no match found, mark it for the next step
                territory.boundary_status = NestedTerritory.BoundaryStatus.NEEDS_WIKI_SCRAPE
                territory.save(update_fields=['boundary_status'])
                marked_for_scraping_count += 1

        # --- Final Summary ---
        self.stdout.write("\n" + self.style.SUCCESS('Import Complete!'))
        self.stdout.write(f'- {updated_count} territories were successfully matched and updated.')
        self.stdout.write(f'- {marked_for_scraping_count} territories could not be matched and were marked for Wikipedia scraping.')
