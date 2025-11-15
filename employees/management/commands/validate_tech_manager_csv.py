# employees/management/commands/validate_tech_manager_csv.py
import csv
import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from employees.models import EmployeeProfile

class Command(BaseCommand):
    help = 'Validates managers and technicians from a CSV file against the database and can optionally fix discrepancies.'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='The path to the CSV file containing manager and technician data.'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Automatically updates EmployeeProfile roles/codes and User names to match CSV data, and creates missing EmployeeProfiles for existing Users. Will NOT rename users if code matches but name is significantly different.'
        )

    def handle(self, *args, **options):
        csv_file_path = options['csv_file']
        fix_mode = options['fix']

        if not os.path.exists(csv_file_path):
            raise CommandError(f"File not found at: {csv_file_path}")

        self.stdout.write(self.style.HTTP_INFO(f"Starting validation from: {csv_file_path} (Fix mode: {fix_mode})"))

        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                header = next(reader)  # Skip header row

                self.stdout.write(self.style.NOTICE(f"CSV Header: {', '.join(header)}"))

                row_num = 1
                for row in reader:
                    row_num += 1
                    if not row or len(row) < 3:
                        self.stdout.write(self.style.WARNING(f"Skipping malformed row {row_num}: {row}"))
                        continue

                    manager_full_name = row[0].strip()
                    technician_code = row[1].strip()
                    technician_full_name = row[2].strip()

                    # Split technician name for lookup
                    technician_parts = technician_full_name.split(' ', 1)
                    csv_tech_first_name = technician_parts[0]
                    csv_tech_last_name = technician_parts[1] if len(technician_parts) > 1 else ''

                    self.stdout.write(self.style.HTTP_INFO(f"\n--- Row {row_num} ---"))
                    self.stdout.write(f"Manager: {manager_full_name}, Technician Code: {technician_code}, Technician Name: {technician_full_name}")

                    # Validate Manager (unchanged, as it seems to be working)
                    manager_profile = None
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
                            self.stdout.write(self.style.ERROR(f"  Manager '{manager_full_name}' not found in User model."))
                        except EmployeeProfile.DoesNotExist:
                            self.stdout.write(self.style.ERROR(f"  Manager '{manager_full_name}' found as User, but no EmployeeProfile with MANAGER role."))
                        except EmployeeProfile.MultipleObjectsReturned:
                            self.stdout.write(self.style.ERROR(f"  Multiple EmployeeProfiles found for Manager '{manager_full_name}' with MANAGER role. Manual review needed."))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"  Error validating manager '{manager_full_name}': {e}"))
                    else:
                        self.stdout.write(self.style.WARNING("  Manager name is empty."))

                    # Validate Technician
                    technician_profile = None
                    technician_user = None
                    
                    # --- Lookup Strategy ---
                    # 1. Try to find a perfect match by code AND name
                    perfect_match_profiles = EmployeeProfile.objects.filter(
                        code=technician_code,
                        user__first_name__iexact=csv_tech_first_name,
                        user__last_name__iexact=csv_tech_last_name
                    )

                    if perfect_match_profiles.count() == 1:
                        technician_profile = perfect_match_profiles.first()
                        technician_user = technician_profile.user
                        self.stdout.write(self.style.SUCCESS(f"  Technician '{technician_full_name}' (Code: {technician_code}) found by perfect match (PK: {technician_profile.pk})."))

                        # Check/fix role if needed
                        if technician_profile.role != EmployeeProfile.Role.TECHNICIAN:
                            self.stdout.write(self.style.WARNING(f"    - Role discrepancy: DB role is '{technician_profile.get_role_display()}' (expected 'TECHNICIAN')."))
                            if fix_mode:
                                with transaction.atomic():
                                    self.stdout.write(self.style.NOTICE(f"    - --fix enabled: Updating EmployeeProfile role to TECHNICIAN."))
                                    technician_profile.role = EmployeeProfile.Role.TECHNICIAN
                                    technician_profile.save(update_fields=['role'])
                                    self.stdout.write(self.style.SUCCESS(f"      EmployeeProfile role updated to TECHNICIAN."))
                        continue # Move to next row, this technician is resolved

                    elif perfect_match_profiles.count() > 1:
                        self.stdout.write(self.style.ERROR(f"  Multiple EmployeeProfiles found for Technician '{technician_full_name}' (Code: {technician_code}) with perfect name/code match. Manual review needed."))
                        continue

                    # 2. If no perfect match, try to find by code only
                    code_match_profiles = EmployeeProfile.objects.filter(code=technician_code)
                    if code_match_profiles.count() == 1:
                        potential_profile = code_match_profiles.first()
                        potential_user = potential_profile.user
                        db_full_name = f"{potential_user.first_name} {potential_user.last_name}".strip()

                        # CRITICAL CHECK: If code matches but names are significantly different, report and skip.
                        if db_full_name.lower() != technician_full_name.lower():
                            self.stdout.write(self.style.ERROR(f"  CRITICAL CONFLICT: Technician code '{technician_code}' matches EmployeeProfile (PK: {potential_profile.pk}) for '{db_full_name}', but CSV expects '{technician_full_name}'. These appear to be different users sharing a code or a data entry error."))
                            self.stdout.write(self.style.ERROR("    - This requires manual investigation. No automatic fix will be applied to prevent data corruption."))
                            continue # IMPORTANT: Skip this row entirely if critical conflict

                        # If we reach here, code matches and names are similar (case-insensitive).
                        technician_profile = potential_profile
                        technician_user = potential_user
                        self.stdout.write(self.style.SUCCESS(f"  Technician '{technician_full_name}' (Code: {technician_code}) found by code (PK: {technician_profile.pk}) with similar name."))
                        
                        # Check/fix role if needed
                        if technician_profile.role != EmployeeProfile.Role.TECHNICIAN:
                            self.stdout.write(self.style.WARNING(f"    - Role discrepancy: DB role is '{technician_profile.get_role_display()}' (expected 'TECHNICIAN')."))
                            if fix_mode:
                                with transaction.atomic():
                                    self.stdout.write(self.style.NOTICE(f"    - --fix enabled: Updating EmployeeProfile role to TECHNICIAN."))
                                    technician_profile.role = EmployeeProfile.Role.TECHNICIAN
                                    technician_profile.save(update_fields=['role'])
                                    self.stdout.write(self.style.SUCCESS(f"      EmployeeProfile role updated to TECHNICIAN."))
                        continue # Move to next row, this technician is resolved

                    elif code_match_profiles.count() > 1:
                        self.stdout.write(self.style.ERROR(f"  Multiple EmployeeProfiles found for Technician code '{technician_code}'. Manual review needed."))
                        continue

                    # 3. If no match by code (perfect or code-only), try to find by name only
                    name_match_users = User.objects.filter(
                        first_name__iexact=csv_tech_first_name,
                        last_name__iexact=csv_tech_last_name
                    )

                    if name_match_users.count() == 1:
                        technician_user = name_match_users.first()
                        self.stdout.write(self.style.NOTICE(f"  Technician '{technician_full_name}' found by name in User model."))
                        technician_profile = EmployeeProfile.objects.filter(user=technician_user).first()

                        if technician_profile:
                            # User and EmployeeProfile exist, but code or role is wrong/missing
                            self.stdout.write(self.style.WARNING(f"    - EmployeeProfile (PK: {technician_profile.pk}) exists for this user but has code '{technician_profile.code}' (expected '{technician_code}') or role '{technician_profile.get_role_display()}' (expected 'TECHNICIAN')."))
                            if fix_mode:
                                with transaction.atomic():
                                    self.stdout.write(self.style.NOTICE(f"    - --fix enabled: Updating EmployeeProfile code to '{technician_code}' and role to TECHNICIAN."))
                                    technician_profile.code = technician_code
                                    technician_profile.role = EmployeeProfile.Role.TECHNICIAN
                                    technician_profile.save(update_fields=['code', 'role'])
                                    self.stdout.write(self.style.SUCCESS(f"      EmployeeProfile updated (PK: {technician_profile.pk})."))
                            else:
                                self.stdout.write(self.style.NOTICE("    - Run with --fix to update EmployeeProfile code and role."))

                        else:
                            # User exists, but no EmployeeProfile
                            self.stdout.write(self.style.WARNING(f"    - User '{technician_full_name}' exists, but no EmployeeProfile found. Creating one."))
                            if fix_mode:
                                with transaction.atomic():
                                    technician_profile = EmployeeProfile.objects.create(
                                        user=technician_user,
                                        code=technician_code,
                                        role=EmployeeProfile.Role.TECHNICIAN
                                    )
                                    self.stdout.write(self.style.SUCCESS(f"    - --fix enabled: EmployeeProfile created (PK: {technician_profile.pk})."))
                            else:
                                self.stdout.write(self.style.NOTICE("    - Run with --fix to create missing EmployeeProfile."))
                        continue # Move to next row, this technician is resolved

                    elif name_match_users.count() > 1:
                        self.stdout.write(self.style.ERROR(f"  Multiple Users found for Technician name '{technician_full_name}'. Manual review needed."))
                        continue

                    # 4. No match found by code or name
                    self.stdout.write(self.style.ERROR(f"  Technician '{technician_full_name}' (Code: {technician_code}) not found in User model or by code. User and EmployeeProfile are missing."))
                    self.stdout.write(self.style.NOTICE("    - Manual creation of User and EmployeeProfile is required for this entry."))

        except FileNotFoundError:
            raise CommandError(f"The file '{csv_file_path}' was not found.")
        except Exception as e:
            raise CommandError(f"An unexpected error occurred while processing the CSV file: {e}")

        self.stdout.write(self.style.HTTP_INFO("\nValidation complete."))
