import csv
from django.core.management.base import BaseCommand
from employees.models import EmployeeProfile
from address.models import FSA
from collections import defaultdict

class Command(BaseCommand):
    help = 'Validates FSA technician assignments against a master CSV file.'

    def handle(self, *args, **options):
        csv_file_path = '/Users/louis-philippedavid/Sites/Hobart/DL/Static data/Hobart_fsa_thech_code.csv'
        
        # --- Step 1: Read all data from CSV and DB ---
        csv_assignments = set()
        csv_tech_codes = set()
        try:
            with open(csv_file_path, 'r', encoding='utf-8-sig') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    if not row: continue
                    fsa_code, tech_code = row[0].strip().upper(), row[1].strip()
                    if not fsa_code or not tech_code: continue
                    csv_assignments.add((fsa_code, tech_code))
                    csv_tech_codes.add(tech_code)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"CSV file not found at: {csv_file_path}"))
            return

        db_tech_profiles = {p.code: p for p in EmployeeProfile.objects.filter(role=EmployeeProfile.Role.TECHNICIAN)}
        db_all_profiles = {p.code: p for p in EmployeeProfile.objects.all()}
        
        db_assignments = set()
        for tech in db_tech_profiles.values():
            for fsa in tech.responsible_fsas.all():
                db_assignments.add((fsa.code, tech.code))

        # --- Part 1: Validate Technicians in the CSV ---
        self.stdout.write(self.style.HTTP_INFO("\n--- Part 1: Validating Technicians from CSV ---"))
        part1_ok = True
        for code in sorted(list(csv_tech_codes)):
            if code not in db_all_profiles:
                self.stdout.write(self.style.ERROR(f"  - ERROR: Tech code '{code}' from CSV does not exist in EmployeeProfile."))
                part1_ok = False
            elif db_all_profiles[code].role != EmployeeProfile.Role.TECHNICIAN:
                self.stdout.write(self.style.WARNING(f"  - WARNING: Tech code '{code}' from CSV exists, but role is '{db_all_profiles[code].get_role_display()}'. Not a Technician."))
                part1_ok = False
        if part1_ok:
            self.stdout.write(self.style.SUCCESS("  All technician codes from the CSV are valid technicians in the database."))

        # --- Part 2: Validate Technicians in the Database ---
        self.stdout.write(self.style.HTTP_INFO("\n--- Part 2: Validating Database Technicians against CSV ---"))
        db_tech_codes = set(db_tech_profiles.keys())
        unlisted_techs = db_tech_codes - csv_tech_codes
        if unlisted_techs:
            self.stdout.write(self.style.NOTICE(f"  - INFO: {len(unlisted_techs)} technicians exist in the DB but are not in the CSV. They may be promoted or inactive:"))
            for code in sorted(list(unlisted_techs)):
                tech = db_tech_profiles[code]
                self.stdout.write(f"    - {tech.user.get_full_name()} (Code: {code})")
        else:
            self.stdout.write(self.style.SUCCESS("  All technicians in the database are listed in the CSV file."))

        # --- Part 3: Validate the Assignments Themselves ---
        self.stdout.write(self.style.HTTP_INFO("\n--- Part 3: Validating FSA Assignments ---"))
        
        # Check 1: Assignments in CSV but not in DB
        missing_in_db = csv_assignments - db_assignments
        if missing_in_db:
            self.stdout.write(self.style.ERROR(f"  - CONFLICT: {len(missing_in_db)} assignments from the CSV are MISSING in the database:"))
            for fsa, tech in sorted(list(missing_in_db)):
                self.stdout.write(f"    - FSA '{fsa}' should be assigned to Tech '{tech}'.")
        else:
            self.stdout.write(self.style.SUCCESS("  All assignments from the CSV exist in the database."))

        # Check 2: Assignments in DB but not in CSV
        extra_in_db = db_assignments - csv_assignments
        if extra_in_db:
            self.stdout.write(self.style.WARNING(f"  - CONFLICT: {len(extra_in_db)} assignments exist in the database but are NOT IN the CSV (obsolete assignments):"))
            for fsa, tech in sorted(list(extra_in_db)):
                self.stdout.write(f"    - FSA '{fsa}' is assigned to Tech '{tech}' in the DB but shouldn't be.")
        else:
            self.stdout.write(self.style.SUCCESS("  No obsolete assignments found in the database."))

        self.stdout.write(self.style.SUCCESS("\n--- Validation Finished ---"))
