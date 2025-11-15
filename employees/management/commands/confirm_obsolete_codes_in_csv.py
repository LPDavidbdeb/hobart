import csv
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from employees.models import EmployeeProfile

class Command(BaseCommand):
    help = 'Confirms if obsolete technician codes for promoted managers exist in the master CSV file.'

    def _get_manager_profile(self, technician_profile):
        """Finds a duplicate Manager profile for the same person."""
        user = technician_profile.user
        duplicate_users = User.objects.filter(
            first_name__iexact=user.first_name,
            last_name__iexact=user.last_name
        ).exclude(pk=user.pk)
        if not duplicate_users.exists():
            return None
        return EmployeeProfile.objects.filter(
            user__in=duplicate_users,
            role=EmployeeProfile.Role.MANAGER
        ).first()

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("--- Checking for Obsolete Tech Codes in Master CSV ---"))
        
        csv_file_path = '/Users/louis-philippedavid/Sites/Hobart/DL/Static data/Hobart_fsa_thech_code.csv'
        
        # Step 1: Read all tech codes from the CSV into a set for fast lookups.
        csv_tech_codes = set()
        try:
            with open(csv_file_path, 'r', encoding='utf-8-sig') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    if len(row) > 1 and row[1]:
                        csv_tech_codes.add(row[1].strip())
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"FATAL: CSV file not found at: {csv_file_path}"))
            return

        self.stdout.write(f"Found {len(csv_tech_codes)} unique technician codes in the CSV file.")

        # Step 2: Find all promoted technicians in the database.
        all_technicians = EmployeeProfile.objects.filter(role=EmployeeProfile.Role.TECHNICIAN)
        
        promoted_tech_profiles = []
        for tech_profile in all_technicians:
            if self._get_manager_profile(tech_profile):
                promoted_tech_profiles.append(tech_profile)

        if not promoted_tech_profiles:
            self.stdout.write(self.style.SUCCESS("No promoted employees with obsolete technician profiles were found."))
            return

        self.stdout.write(self.style.HTTP_INFO("\n--- Verifying Promoted Employee Codes ---"))
        
        # Step 3: Check if their obsolete code is in the CSV.
        for tech_profile in promoted_tech_profiles:
            obsolete_code = tech_profile.code
            employee_name = tech_profile.user.get_full_name()

            if obsolete_code in csv_tech_codes:
                self.stdout.write(self.style.SUCCESS(
                    f"  - CONFIRMED: Obsolete code '{obsolete_code}' for promoted manager '{employee_name}' was found in the CSV."
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"  - NOT FOUND: Obsolete code '{obsolete_code}' for promoted manager '{employee_name}' was NOT found in the CSV."
                ))

        self.stdout.write(self.style.SUCCESS("\n--- Script Finished ---"))
