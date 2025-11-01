import json
from django.core.management.base import BaseCommand
from django.db import transaction
from django.apps import apps
from django.core.serializers import deserialize

class Command(BaseCommand):
    help = 'Loads data from a JSON fixture, excluding specific models.'

    def add_arguments(self, parser):
        parser.add_argument('fixture_path', type=str, help='Path to the JSON fixture file.')

    def handle(self, *args, **options):
        fixture_path = options['fixture_path']
        # Models to exclude from the loading process
        excluded_models = {'organization.nestedterritory', 'contenttypes.contenttype', 'auth.permission'}

        self.stdout.write(self.style.SUCCESS(f"Starting data load from {fixture_path}"))
        self.stdout.write(self.style.WARNING(f"Excluding models: {', '.join(excluded_models)}"))

        try:
            with open(fixture_path, 'r') as f:
                objects = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Fixture file not found at: {fixture_path}"))
            return
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f"Error decoding JSON: {e}"))
            return

        # Filter out the excluded models
        filtered_objects = [obj for obj in objects if obj['model'] not in excluded_models]
        self.stdout.write(f"Found {len(objects)} total objects, loading {len(filtered_objects)}.")

        # Use Django's deserializer to handle object creation
        # This is more robust than manually creating objects
        deserialized_objects = deserialize("json", json.dumps(filtered_objects))

        self.stdout.write("Saving objects to the database...")
        with transaction.atomic():
            for obj in deserialized_objects:
                # The deserializer creates model instances. We just need to save them.
                # This respects database relations and is safer than raw SQL.
                obj.save()

        self.stdout.write(self.style.SUCCESS("Data load complete!"))
