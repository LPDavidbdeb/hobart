import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.gis.utils import LayerMapping
from address.models import FSA

class Command(BaseCommand):
    help = 'Import FSA data from a shapefile and label it as official census data.'

    def add_arguments(self, parser):
        parser.add_argument('shapefile', type=str, help='The absolute path to the shapefile to import.')

    def handle(self, *args, **options):
        shapefile_path = options['shapefile']

        if not os.path.exists(shapefile_path):
            raise CommandError(f'Shapefile not found at: {shapefile_path}')

        # Mapping based on the French shapefile documentation
        fsa_mapping = {
            'code': 'RTACIDU',      # The 3-character FSA code
            'cfsa_uid': 'IDUGD',      # The 21-character unique identifier
            'pruid': 'PRIDU',
            'land_area': 'SUPTERRE',   # Land area in square kilometers
            'boundary': 'MULTIPOLYGON',
        }

        try:
            self.stdout.write(f"Starting import from {shapefile_path}...")
            lm = LayerMapping(FSA, shapefile_path, fsa_mapping, transform=False, encoding='iso-8859-1')
            lm.save(strict=True, verbose=True)
            self.stdout.write(self.style.SUCCESS('Successfully imported FSA shapefile data.'))

            # Now, label the imported data as being from the census
            self.stdout.write("  -> Labeling imported data as official census data...")
            updated_count = FSA.objects.filter(cfsa_uid__isnull=False).update(
                source=FSA.Source.CENSUS,
                boundary_type=FSA.BoundaryType.OFFICIAL
            )
            self.stdout.write(self.style.SUCCESS(f"     {updated_count} records labeled as CENSUS source."))

        except Exception as e:
            raise CommandError(f'Error importing FSA data: {e}')
