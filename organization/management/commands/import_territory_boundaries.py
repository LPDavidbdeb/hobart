import json
from django.core.management.base import BaseCommand, CommandError
from organization.models import Territory
from django.db import transaction

class Command(BaseCommand):
    help = 'Imports geographical boundary data (GeoJSON) for Territory objects.'

    def add_arguments(self, parser):
        parser.add_argument('geojson_file', type=str, help='Path to the GeoJSON file.')
        parser.add_argument('--territory_type', type=str, required=True,
                            choices=[t.value for t in Territory.TerritoryType],
                            help='The type of territory being imported (e.g., PROVINCE, REGION, CITY).')
        parser.add_argument('--name_property', type=str, default='name',
                            help='The GeoJSON property key that contains the territory name.')

    def handle(self, *args, **options):
        geojson_file_path = options['geojson_file']
        territory_type = options['territory_type']
        name_property = options['name_property']

        self.stdout.write(f"Attempting to import {territory_type} boundaries from {geojson_file_path}...")

        try:
            with open(geojson_file_path, 'r') as f:
                geojson_data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'GeoJSON file not found at "{geojson_file_path}"')
        except json.JSONDecodeError:
            raise CommandError(f'Invalid GeoJSON format in "{geojson_file_path}"')

        if geojson_data.get('type') != 'FeatureCollection':
            raise CommandError('GeoJSON file must be a FeatureCollection.')

        imported_count = 0
        updated_count = 0
        skipped_count = 0

        with transaction.atomic():
            for feature in geojson_data.get('features', []):
                properties = feature.get('properties', {})
                geometry = feature.get('geometry')

                if not geometry:
                    self.stdout.write(self.style.WARNING(f"Skipping feature with no geometry: {properties.get(name_property, 'N/A')}"))
                    skipped_count += 1
                    continue

                territory_name = properties.get(name_property)
                if not territory_name:
                    self.stdout.write(self.style.WARNING(f"Skipping feature with no '{name_property}' property."))
                    skipped_count += 1
                    continue

                try:
                    territory = Territory.objects.get(name=territory_name, type=territory_type)
                    territory.boundary_geojson = geometry
                    territory.save()
                    updated_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Updated boundary for {territory_name} ({territory_type})."))
                except Territory.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Skipping GeoJSON feature '{territory_name}' ({territory_type}): No matching Territory found in database."))
                    skipped_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error processing '{territory_name}' ({territory_type}): {e}"))
                    skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Import complete. Updated {updated_count} territories, skipped {skipped_count} features."
        ))
