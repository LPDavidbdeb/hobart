import time
import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from address.models import FSA

class Command(BaseCommand):
    help = 'Backfills the center_point for existing FSAs that are marked as INFERRED and do not have one.'

    def handle(self, *args, **options):
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if not api_key:
            self.stdout.write(self.style.ERROR("ERROR: GOOGLE_MAPS_API_KEY not found in settings. Cannot geocode FSAs."))
            return

        # Filter for FSAs that are INFERRED and are missing a center_point
        fsas_to_update = FSA.objects.filter(
            source=FSA.Source.INFERRED, 
            center_point__isnull=True
        )
        total_fsas = fsas_to_update.count()

        if total_fsas == 0:
            self.stdout.write(self.style.SUCCESS("All inferred FSAs already have a center point. Nothing to do."))
            return

        self.stdout.write(f"Found {total_fsas} inferred FSAs missing a center point. Starting backfill...")

        for i, fsa in enumerate(fsas_to_update):
            self.stdout.write(f"Processing {i + 1}/{total_fsas}: {fsa.code}...")
            
            try:
                response = requests.get(
                    'https://maps.googleapis.com/maps/api/geocode/json',
                    params={'address': f'{fsa.code}, Canada', 'key': api_key}
                )
                response.raise_for_status()
                data = response.json()

                if data['status'] == 'OK':
                    location = data['results'][0]['geometry']['location']
                    fsa.center_point = Point(location['lng'], location['lat'], srid=4326)
                    fsa.save()
                    self.stdout.write(self.style.SUCCESS(f"  - Successfully updated {fsa.code}."))
                elif data['status'] == 'OVER_QUERY_LIMIT':
                    self.stdout.write(self.style.ERROR("  - Google API query limit reached. Please wait and try again later."))
                    break
                else:
                    self.stdout.write(self.style.WARNING(f"  - Could not geocode {fsa.code}. Google API status: {data['status']}"))

            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"  - An error occurred while geocoding {fsa.code}: {e}"))
            
            # Add a small delay to respect API rate limits
            time.sleep(0.1)

        self.stdout.write(self.style.SUCCESS("\nBackfill script finished."))
