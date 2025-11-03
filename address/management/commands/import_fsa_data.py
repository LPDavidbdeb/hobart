import os
from django.core.management.base import BaseCommand
from django.contrib.gis.utils import LayerMapping
from address.models import FSA

class Command(BaseCommand):
    help = 'Import FSA data from a shapefile.'

    def add_arguments(self, parser):
        parser.add_argument('shapefile', type=str, help='The absolute path to the shapefile to import.')

    def handle(self, *args, **options):
        shapefile_path = options['shapefile']

        if not os.path.exists(shapefile_path):
            self.stdout.write(self.style.ERROR(f'Shapefile not found at: {shapefile_path}'))
            return

        fsa_mapping = {
            'code': 'CFSAUID',
            'pruid': 'PRUID',
            'boundary': 'MULTIPOLYGON',
        }

        try:
            lm = LayerMapping(FSA, shapefile_path, fsa_mapping, transform=False, encoding='iso-8859-1')
            lm.save(strict=True, verbose=True)
            self.stdout.write(self.style.SUCCESS('Successfully imported FSA data.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error importing FSA data: {e}'))
