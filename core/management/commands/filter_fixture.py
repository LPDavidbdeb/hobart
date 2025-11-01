import json
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Filters a large JSON fixture file to include only specific models.'

    def add_arguments(self, parser):
        parser.add_argument(
            'input_file',
            type=str,
            help='The path to the input JSON fixture file.'
        )
        parser.add_argument(
            'output_file',
            type=str,
            help='The path for the new, filtered JSON fixture file.'
        )
        parser.add_argument(
            'models',
            nargs='+',
            type=str,
            help='A list of models to include, in the format app_label.ModelName (e.g., client.client).'
        )

    def handle(self, *args, **options):
        input_path = options['input_file']
        output_path = options['output_file']
        models_to_keep = options['models']

        self.stdout.write(f"Reading from fixture: {input_path}")
        self.stdout.write(f"Filtering for models: {models_to_keep}")

        try:
            with open(input_path, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Input file not found: {input_path}"))
            return
        except json.JSONDecodeError:
            self.stdout.write(self.style.ERROR(f"Could not parse JSON from: {input_path}"))
            return

        filtered_data = []
        for obj in data:
            if obj.get('model') in models_to_keep:
                filtered_data.append(obj)

        self.stdout.write(f"Found {len(filtered_data)} objects to keep.")

        try:
            with open(output_path, 'w') as f:
                json.dump(filtered_data, f, indent=2)
        except IOError as e:
            self.stdout.write(self.style.ERROR(f"Could not write to output file: {e}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Successfully created filtered fixture: {output_path}"
        ))
