import csv
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from employees.models import EmployeeProfile
from address.models import FSA
from employees.utils import create_employee

class Command(BaseCommand):
    help = 'Imports technician-FSA assignments from a CSV file.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='The path to the CSV file to import.')

    @transaction.atomic
    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        self.stdout.write(self.style.SUCCESS(f"Starting import from {csv_file_path}..."))

        unmatched_assignments = {}
        successful_assignments = 0

        try:
            with open(csv_file_path, mode='r', encoding='utf-8-sig') as file:
                reader = csv.reader(file)
                header = next(reader)

                for row in reader:
                    if not row:
                        continue

                    fsa_code_raw, employee_code_raw = row
                    fsa_code = fsa_code_raw.strip()
                    employee_code = employee_code_raw.strip()

                    if not fsa_code or not employee_code:
                        self.stdout.write(self.style.WARNING(f"Skipping row with empty data: {row}"))
                        continue

                    fsa, created = FSA.objects.get_or_create(
                        code=fsa_code,
                        defaults={'source': FSA.Source.INFERRED}
                    )
                    if created:
                        self.stdout.write(f"Created new FSA '{fsa_code}' with source 'INFERRED'.")

                    try:
                        technician = EmployeeProfile.objects.get(code=employee_code, role=EmployeeProfile.Role.TECHNICIAN)
                        technician.responsible_fsas.add(fsa)
                        successful_assignments += 1
                    except EmployeeProfile.DoesNotExist:
                        if employee_code not in unmatched_assignments:
                            unmatched_assignments[employee_code] = []
                        unmatched_assignments[employee_code].append(fsa)

        except FileNotFoundError:
            raise CommandError(f"File not found at: {csv_file_path}")
        except Exception as e:
            raise CommandError(f"An error occurred during file processing: {e}")

        self.stdout.write(self.style.SUCCESS(f"Phase 1 Complete: {successful_assignments} FSAs assigned to existing technicians."))

        if unmatched_assignments:
            self.stdout.write(self.style.WARNING(f"Found {len(unmatched_assignments)} unmatched technician codes. Entering interactive creation mode..."))
            for code, fsas in unmatched_assignments.items():
                self.stdout.write("---")
                self.stdout.write(f"Could not find a technician with legacy code: '{code}'")
                self.stdout.write("To create this technician, please provide their details. (Leave blank to skip)")
                
                first_name = input("First Name: ").strip()
                if not first_name:
                    self.stdout.write(self.style.WARNING(f"Skipping technician with code '{code}'."))
                    continue

                last_name = input("Last Name: ").strip()
                if not last_name:
                    self.stdout.write(self.style.WARNING(f"Last name cannot be empty. Skipping technician with code '{code}'."))
                    continue

                try:
                    user_data = {'first_name': first_name, 'last_name': last_name}
                    new_technician = create_employee(
                        role=EmployeeProfile.Role.TECHNICIAN,
                        code=code,
                        **user_data
                    )
                    
                    for fsa in fsas:
                        new_technician.responsible_fsas.add(fsa)
                    
                    self.stdout.write(self.style.SUCCESS(f"Successfully created technician '{first_name} {last_name}' with code '{code}' and assigned {len(fsas)} FSAs."))

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Could not create technician for code '{code}'. Reason: {e}"))
        else:
            self.stdout.write(self.style.SUCCESS("All technician codes matched successfully!"))

        self.stdout.write(self.style.SUCCESS("Import process finished."))
