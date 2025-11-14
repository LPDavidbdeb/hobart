import csv
import re
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from employees.models import EmployeeProfile
from address.models import PostalCode
import googlemaps
from django.contrib.gis.geos import Point
from django.utils import timezone

class Command(BaseCommand):
    help = 'Imports technician postal codes from a CSV file, geocodes them, and links them to employees.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='The path to the CSV file to import.')

    def handle(self, *args, **options):
        if not hasattr(settings, 'GOOGLE_MAPS_API_KEY') or not settings.GOOGLE_MAPS_API_KEY:
            raise CommandError("GOOGLE_MAPS_API_KEY setting is not configured.")

        gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
        csv_file_path = options['csv_file']

        updated_count = 0
        not_found_count = 0
        newly_geocoded_count = 0
        unmatched_names = []

        try:
            with open(csv_file_path, mode='r', encoding='utf-8-sig') as infile:
                reader = csv.reader(infile)
                next(reader)  # Skip header row

                for row in reader:
                    full_name, postal_code_str = row
                    
                    # Clean up postal code
                    postal_code_str = postal_code_str.strip().upper().replace(' ', '')
                    if not postal_code_str:
                        continue

                    # --- Find Employee by Name ---
                    # This is a simple matching logic. It can be improved with fuzzy matching libraries if needed.
                    name_parts = [part.strip() for part in full_name.replace('"', '').split(',')]
                    last_name, first_name = name_parts[0], name_parts[1]

                    employee = EmployeeProfile.objects.filter(
                        Q(user__first_name__iexact=first_name, user__last_name__iexact=last_name) |
                        Q(user__first_name__iexact=last_name, user__last_name__iexact=first_name)
                    ).first()

                    if not employee:
                        self.stdout.write(self.style.WARNING(f"Could not find employee for name: '{full_name}'"))
                        not_found_count += 1
                        unmatched_names.append(full_name)
                        continue

                    # --- Get or Create and Geocode PostalCode ---
                    postal_code_obj, created = PostalCode.objects.get_or_create(code=postal_code_str)

                    if created or not postal_code_obj.location:
                        self.stdout.write(f"Geocoding new postal code: {postal_code_str}...")
                        try:
                            geocode_result = gmaps.geocode(f'{postal_code_str}, Canada')
                            if geocode_result:
                                location = geocode_result[0]['geometry']['location']
                                lat, lng = location['lat'], location['lng']
                                postal_code_obj.latitude = lat
                                postal_code_obj.longitude = lng
                                postal_code_obj.location = Point(lng, lat, srid=4326)
                                postal_code_obj.last_geocoded = timezone.now()
                                postal_code_obj.save()
                                newly_geocoded_count += 1
                            else:
                                self.stdout.write(self.style.ERROR(f"Could not geocode postal code: {postal_code_str}"))
                                continue
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"Error geocoding {postal_code_str}: {e}"))
                            continue
                    
                    # --- Link Employee to PostalCode ---
                    employee.postal_code = postal_code_obj
                    employee.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Successfully linked {employee.user.get_full_name()} to {postal_code_str}"))

        except FileNotFoundError:
            raise CommandError(f'File "{csv_file_path}" does not exist.')

        self.stdout.write("\n--- Import Summary ---")
        self.stdout.write(self.style.SUCCESS(f"Successfully updated {updated_count} employees."))
        self.stdout.write(self.style.WARNING(f"Could not find {not_found_count} employees."))
        self.stdout.write(f"Newly geocoded {newly_geocoded_count} postal codes.")
        if unmatched_names:
            self.stdout.write("\nUnmatched names:")
            for name in unmatched_names:
                self.stdout.write(f"- {name}")
        self.stdout.write("\n--- End of Report ---")
