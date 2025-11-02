import unicodedata
import difflib
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import MultiPolygon
from organization.models import NestedTerritory

# A list of common terms to remove from names for better matching
TERMS_TO_REMOVE = [
    'regional municipality of', 'regional district of', 'county of', 'municipal district of', 
    'improvement district', 'regional district', 'municipal disctrict of', 'united counties of',
    'comtes unis de', 'municipalite regionale de comte', 'mrc de',
    'county', 'district', 'region', 'regional', 'municipality', 'municipal'
]

def clean_name(name):
    """Removes common terms, numbers, and normalizes the string."""
    if not name:
        return ""
    
    # Normalize to lowercase and remove accents
    nfkd_form = unicodedata.normalize('NFKD', name.lower())
    normalized = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    
    # Remove common administrative terms
    for term in TERMS_TO_REMOVE:
        normalized = normalized.replace(term, '')
        
    # Remove numbers and common separators
    normalized = re.sub(r'[\d\-/\.]+', '', normalized)
    
    # Strip leading/trailing whitespace
    return normalized.strip()


class Command(BaseCommand):
    help = 'Interactively match and import boundaries for REGION territories that are missing them.'

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

        self.stdout.write('Loading and cleaning shapefile features...')
        ds = DataSource(shapefile_path)
        layer = ds[0]

        # Map cleaned shapefile names back to their original name and data
        shapefile_map = {clean_name(f.get(name_field)): {'original': f.get(name_field), 'geom': f.geom, 'code': f.get(code_field)} for f in layer if f.get(name_field)}
        cleaned_shapefile_names = list(shapefile_map.keys())
        self.stdout.write(f'  -> Found {len(shapefile_map)} features in shapefile.\n')

        unmapped_regions = list(NestedTerritory.objects.filter(type=NestedTerritory.TerritoryType.REGION, boundary__isnull=True))

        if not unmapped_regions:
            self.stdout.write(self.style.SUCCESS('All REGION territories already have boundaries. Nothing to do.'))
            return

        self.stdout.write(self.style.WARNING(f'Found {len(unmapped_regions)} REGION territories missing boundaries. Starting interactive matching...'))
        self.stdout.write("Enter the number of the correct match, 's' to skip, or 'q' to quit.")

        for i, territory in enumerate(unmapped_regions):
            self.stdout.write("-" * 50)
            self.stdout.write(f"({i+1}/{len(unmapped_regions)}) Matching DB Territory: ", ending='')
            self.stdout.write(self.style.SUCCESS(territory.name))

            cleaned_db_name = clean_name(territory.name)
            close_matches_cleaned = difflib.get_close_matches(cleaned_db_name, cleaned_shapefile_names, n=5, cutoff=0.8)

            if not close_matches_cleaned:
                self.stdout.write(self.style.WARNING('  -> No close matches found. Skipping.'))
                continue

            # Get the original names for display
            close_matches_original = [shapefile_map[name]['original'] for name in close_matches_cleaned]

            self.stdout.write("Possible matches from shapefile:")
            for idx, match_name in enumerate(close_matches_original):
                self.stdout.write(f"  [{idx + 1}] {match_name}")

            while True:
                choice = input("Your choice (1-5, s, q): ").lower()
                if choice == 'q':
                    self.stdout.write("Quitting.")
                    return
                if choice == 's':
                    self.stdout.write("Skipped.")
                    break
                
                try:
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(close_matches_cleaned):
                        chosen_cleaned_name = close_matches_cleaned[choice_idx]
                        feature_data = shapefile_map[chosen_cleaned_name]
                        geom = feature_data['geom']
                        code = feature_data['code']

                        if geom.geom_type == 'Polygon':
                            territory.boundary = MultiPolygon(geom.geos)
                        else:
                            territory.boundary = geom.geos
                        
                        territory.code = code
                        territory.save(update_fields=['boundary', 'code'])
                        
                        self.stdout.write(self.style.SUCCESS(f"  -> MATCHED! Saved boundary for '{territory.name}'."))
                        self.stdout.write(self.style.NOTICE(f"    Mapping to add: \"'{territory.name.lower()}': '{feature_data['original'].lower()}'\","))
                        break
                    else:
                        self.stdout.write(self.style.ERROR("Invalid number. Please try again."))
                except (ValueError, IndexError):
                    self.stdout.write(self.style.ERROR("Invalid input. Please enter a number, 's', or 'q'."))

        self.stdout.write("\n" + self.style.SUCCESS('Interactive matching session complete!'))
