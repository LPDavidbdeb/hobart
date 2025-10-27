import csv
from django.core.management.base import BaseCommand, CommandError
from client.models import Client

class Command(BaseCommand):
    help = 'Imports legacy address fields (address1, address2, postal_code) from a CSV file into the Client model.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='The path to the CSV file to import.')

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        self.stdout.write(self.style.SUCCESS(f'Starting import from {csv_file_path}'))

        try:
            with open(csv_file_path, mode='r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                
                updated_count = 0
                not_found_count = 0
                skipped_count = 0

                for row in reader:
                    # Corrected to match the actual CSV headers
                    account_number = row.get('Account')
                    address1 = row.get('Address1', '').strip()
                    address2 = row.get('Address2', '').strip()
                    postal_code = row.get('Postal', '').strip()

                    if not account_number:
                        self.stdout.write(self.style.WARNING(f'Skipping row with no account number: {row}'))
                        skipped_count += 1
                        continue

                    try:
                        client = Client.objects.get(account_number=account_number)
                        client.address1 = address1
                        client.address2 = address2
                        client.postal_code = postal_code
                        client.save(update_fields=['address1', 'address2', 'postal_code'])
                        updated_count += 1
                    except Client.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f'Client with account number {account_number} not found.'))
                        not_found_count += 1

        except FileNotFoundError:
            raise CommandError(f'File not found at: {csv_file_path}')
        except Exception as e:
            raise CommandError(f'An error occurred: {e}')

        self.stdout.write(self.style.SUCCESS('Import complete!'))
        self.stdout.write(f'Successfully updated: {updated_count}')
        self.stdout.write(f'Clients not found: {not_found_count}')
        self.stdout.write(f'Rows skipped: {skipped_count}')
