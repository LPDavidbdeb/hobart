import csv
import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from employees.models import EmployeeProfile

class Command(BaseCommand):
    help = 'Assigns technicians to managers based on a CSV file.'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='The path to the CSV file containing manager and technician data.'
        )

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']

        if not os.path.exists(csv_file_path):
            raise CommandError(f"File not found at: {csv_file_path}")

        self.stdout.write(self.style.HTTP_INFO(f"Starting technician assignment from: {csv_file_path}"))

        successful_assignments = 0
        failed_assignments = 0

        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header row

                row_num = 1
                for row in reader:
                    row_num += 1
                    if not row or len(row) < 3:
                        self.stdout.write(self.style.WARNING(f"Skipping malformed row {row_num}: {row}"))
                        failed_assignments += 1
                        continue

                    manager_full_name = row[0].strip()
                    technician_code = row[1].strip()
                    technician_full_name = row[2].strip()

                    self.stdout.write(self.style.HTTP_INFO(f"\n--- Processing Row {row_num} ---"))
                    self.stdout.write(f"Attempting to assign Technician (Code: {technician_code}, Name: {technician_full_name}) to Manager: {manager_full_name}")

                    manager_profile = None
                    technician_profile = None

                    # 1. Find Manager Profile
                    if manager_full_name:
                        manager_parts = manager_full_name.split(' ', 1)
                        manager_first_name = manager_parts[0]
                        manager_last_name = manager_parts[1] if len(manager_parts) > 1 else ''

                        try:
                            manager_user = User.objects.get(
                                first_name__iexact=manager_first_name,
                                last_name__iexact=manager_last_name
                            )
                            manager_profile = EmployeeProfile.objects.get(
                                user=manager_user,
                                role=EmployeeProfile.Role.MANAGER
                            )
                            self.stdout.write(self.style.SUCCESS(f"  Manager '{manager_full_name}' found (PK: {manager_profile.pk})."))
                        except User.DoesNotExist:
                            self.stdout.write(self.style.ERROR(f"  Manager '{manager_full_name}' not found in User model. Skipping assignment."))
                            failed_assignments += 1
                            continue
                        except EmployeeProfile.DoesNotExist:
                            self.stdout.write(self.style.ERROR(f"  Manager '{manager_full_name}' found as User, but no EmployeeProfile with MANAGER role. Skipping assignment."))
                            failed_assignments += 1
                            continue
                        except EmployeeProfile.MultipleObjectsReturned:
                            self.stdout.write(self.style.ERROR(f"  Multiple EmployeeProfiles found for Manager '{manager_full_name}' with MANAGER role. Manual review needed. Skipping assignment."))
                            failed_assignments += 1
                            continue
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"  Error finding manager '{manager_full_name}': {e}. Skipping assignment."))
                            failed_assignments += 1
                            continue
                    else:
                        self.stdout.write(self.style.WARNING("  Manager name is empty. Skipping assignment."))
                        failed_assignments += 1
                        continue

                    # 2. Find Technician Profile
                    if technician_code and technician_full_name:
                        technician_parts = technician_full_name.split(' ', 1)
                        technician_first_name = technician_parts[0]
                        technician_last_name = technician_parts[1] if len(technician_parts) > 1 else ''

                        try:
                            technician_user = User.objects.get(
                                first_name__iexact=technician_first_name,
                                last_name__iexact=technician_last_name
                            )
                            technician_profile = EmployeeProfile.objects.get(
                                user=technician_user,
                                code=technician_code,
                                role=EmployeeProfile.Role.TECHNICIAN
                            )
                            self.stdout.write(self.style.SUCCESS(f"  Technician '{technician_full_name}' (Code: {technician_code}) found (PK: {technician_profile.pk})."))
                        except User.DoesNotExist:
                            self.stdout.write(self.style.ERROR(f"  Technician '{technician_full_name}' not found in User model. Skipping assignment."))
                            failed_assignments += 1
                            continue
                        except EmployeeProfile.DoesNotExist:
                            self.stdout.write(self.style.ERROR(f"  Technician '{technician_full_name}' found as User, but no EmployeeProfile with TECHNICIAN role and code '{technician_code}'. Skipping assignment."))
                            failed_assignments += 1
                            continue
                        except EmployeeProfile.MultipleObjectsReturned:
                            self.stdout.write(self.style.ERROR(f"  Multiple EmployeeProfiles found for Technician '{technician_full_name}' (Code: {technician_code}) with TECHNICIAN role. Manual review needed. Skipping assignment."))
                            failed_assignments += 1
                            continue
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"  Error finding technician '{technician_full_name}' (Code: {technician_code}): {e}. Skipping assignment."))
                            failed_assignments += 1
                            continue
                    else:
                        self.stdout.write(self.style.WARNING("  Technician code or name is empty. Skipping assignment."))
                        failed_assignments += 1
                        continue

                    # 3. Assign Technician to Manager
                    if manager_profile and technician_profile:
                        with transaction.atomic():
                            if technician_profile.reports_to != manager_profile:
                                technician_profile.reports_to = manager_profile
                                technician_profile.save()
                                self.stdout.write(self.style.SUCCESS(f"  Successfully assigned Technician '{technician_full_name}' to Manager '{manager_full_name}'."))
                                successful_assignments += 1
                            else:
                                self.stdout.write(self.style.NOTICE(f"  Technician '{technician_full_name}' is already assigned to Manager '{manager_full_name}'. No change needed."))
                                successful_assignments += 1 # Count as successful as the state is correct

        except FileNotFoundError:
            raise CommandError(f"The file '{csv_file_path}' was not found.")
        except Exception as e:
            raise CommandError(f"An unexpected error occurred while processing the CSV file: {e}")

        self.stdout.write(self.style.HTTP_INFO("\n--- Assignment Summary ---"))
        self.stdout.write(self.style.SUCCESS(f"Successful assignments: {successful_assignments}"))
        self.stdout.write(self.style.ERROR(f"Failed assignments: {failed_assignments}"))
        self.stdout.write(self.style.HTTP_INFO("Assignment process complete."))