import csv
import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from employees.models import EmployeeProfile
from address.models import FSA

class Command(BaseCommand):
    help = 'Check employee and FSA data against a CSV file and optionally fix duplicates and create inferred FSAs.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Deletes duplicate technician profiles and creates inferred FSAs with geocoded center points.',
        )

    def handle(self, *args, **options):
        csv_file_path = '/Users/louis-philippedavid/Sites/Hobart/DL/Static data/fsa-prenom_nom manager.csv'
        
        # --- Step 1: FSA Validation ---
        self.stdout.write(self.style.HTTP_INFO("--- Starting FSA Validation ---"))
        unique_fsa_codes = set()
        with open(csv_file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)
            for row in reader:
                fsa_code = row[0].strip().upper()
                if len(fsa_code) == 3:
                    unique_fsa_codes.add(fsa_code)

        existing_fsas = set(FSA.objects.filter(code__in=unique_fsa_codes).values_list('code', flat=True))
        missing_fsas = unique_fsa_codes - existing_fsas

        if missing_fsas:
            self.stdout.write(self.style.WARNING(f"Found {len(missing_fsas)} missing FSAs: {', '.join(sorted(list(missing_fsas)))}"))
            if options['fix']:
                self.stdout.write("  --fix is enabled. Creating and geocoding missing FSAs...")
                api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
                if not api_key:
                    self.stdout.write(self.style.ERROR("  ERROR: GOOGLE_MAPS_API_KEY not found in settings. Cannot geocode FSAs."))
                
                for code in missing_fsas:
                    center_point = None
                    if api_key:
                        try:
                            response = requests.get(
                                'https://maps.googleapis.com/maps/api/geocode/json',
                                params={'address': f'{code}, Canada', 'key': api_key}
                            )
                            response.raise_for_status()
                            data = response.json()
                            if data['status'] == 'OK':
                                location = data['results'][0]['geometry']['location']
                                center_point = Point(location['lng'], location['lat'], srid=4326)
                                self.stdout.write(self.style.SUCCESS(f"    - Geocoded {code} successfully."))
                            else:
                                self.stdout.write(self.style.WARNING(f"    - Could not geocode {code}. Google API status: {data['status']}"))
                        except requests.RequestException as e:
                            self.stdout.write(self.style.ERROR(f"    - An error occurred while geocoding {code}: {e}"))

                    FSA.objects.create(code=code, source=FSA.Source.INFERRED, center_point=center_point)
                    self.stdout.write(self.style.SUCCESS(f"    - Created FSA: {code} (Source: INFERRED)"))
            else:
                self.stdout.write(self.style.NOTICE("  Run with --fix to create these FSAs automatically."))
        else:
            self.stdout.write(self.style.SUCCESS("All FSA codes in the CSV already exist in the database."))
        
        self.stdout.write(self.style.HTTP_INFO("--- FSA Validation Complete ---"))

        # --- Step 2: Employee Data Validation ---
        self.stdout.write(self.style.HTTP_INFO("\n--- Starting Employee Data Validation ---"))
        unique_names = set()
        with open(csv_file_path, 'r') as file:
            reader = csv.reader(file)
            next(reader)
            for row in reader:
                name = row[1].strip()
                if name:
                    unique_names.add(name)

        self.stdout.write(f"Found {len(unique_names)} unique names in the CSV file.")

        for name in sorted(list(unique_names)):
            parts = name.split()
            if not parts:
                continue
            
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

            self.stdout.write(f"\nProcessing: {first_name} {last_name}")

            users = User.objects.filter(first_name__iexact=first_name, last_name__iexact=last_name)
            
            if not users.exists():
                self.stdout.write(self.style.WARNING(f"  - NOT FOUND: No user found for '{name}'. This employee needs to be created."))
                continue

            profiles = EmployeeProfile.objects.filter(user__in=users)
            manager_profiles = profiles.filter(role=EmployeeProfile.Role.MANAGER)
            technician_profiles = profiles.filter(role=EmployeeProfile.Role.TECHNICIAN)

            if profiles.count() == 1:
                profile = profiles.first()
                if profile.role == EmployeeProfile.Role.MANAGER:
                    self.stdout.write(self.style.SUCCESS(f"  - OK: Found one profile for '{name}', who is already a Manager."))
                else:
                    self.stdout.write(self.style.NOTICE(f"  - ACTION NEEDED: Found one profile for '{name}', who is a {profile.get_role_display()}. This employee should be promoted to Manager."))

            elif profiles.count() > 1:
                self.stdout.write(self.style.WARNING(f"  - DUPLICATES FOUND: Found {profiles.count()} profiles for '{name}'."))
                if manager_profiles.count() == 1:
                    self.stdout.write(self.style.SUCCESS("    - OK: One of the profiles is correctly identified as a Manager."))
                    for tech_profile in technician_profiles:
                        # Check for responsible FSAs
                        if tech_profile.responsible_fsas.exists():
                            fsa_codes = ", ".join(tech_profile.responsible_fsas.values_list('code', flat=True))
                            self.stdout.write(self.style.ERROR(f"    - DANGER: Technician profile (ID: {tech_profile.id}) has assigned FSAs ({fsa_codes}). These must be migrated before deletion. SKIPPING."))
                        else:
                            # Safe to delete
                            if options['fix']:
                                self.stdout.write(self.style.WARNING(f"    - DELETING: Duplicate Technician profile (ID: {tech_profile.id}, User: {tech_profile.user.username}) with no assigned FSAs."))
                                tech_profile.user.delete()
                            else:
                                self.stdout.write(self.style.NOTICE(f"    - DUPLICATE (Safe to delete): Technician profile (ID: {tech_profile.id}, User: {tech_profile.user.username}) has no assigned FSAs."))
                elif manager_profiles.count() > 1:
                     self.stdout.write(self.style.ERROR(f"    - DUPLICATE: Found {manager_profiles.count()} Manager profiles for '{name}'. Manual review required."))
                else:
                    self.stdout.write(self.style.ERROR(f"    - DUPLICATE: No Manager profile found for '{name}' among the duplicates. Manual review required."))

            else:
                self.stdout.write(self.style.ERROR(f"  - ERROR: User exists for '{name}', but no EmployeeProfile found. This indicates a data inconsistency."))

        if not options['fix']:
            self.stdout.write(self.style.NOTICE("\nRun with --fix to automatically create missing FSAs and delete safe duplicate technician profiles."))

        self.stdout.write(self.style.SUCCESS("\nScript finished."))
