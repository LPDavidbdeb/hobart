from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from employees.models import EmployeeProfile
from employees.utils import generate_unique_employee_email

class Command(BaseCommand):
    help = 'Normalizes existing employee accounts by generating a standard email and setting an unusable password.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('This command will overwrite existing emails and invalidate passwords for all non-superuser employees.'))
        confirmation = input('Are you sure you want to proceed? [y/N] ')

        if confirmation.lower() != 'y':
            self.stdout.write(self.style.ERROR('Operation cancelled.'))
            return

        # Get all employee profiles, excluding superusers
        profiles_to_process = EmployeeProfile.objects.filter(user__is_superuser=False).select_related('user')
        total_profiles = profiles_to_process.count()

        if total_profiles == 0:
            self.stdout.write(self.style.SUCCESS('No non-superuser employee profiles found to process.'))
            return

        self.stdout.write(f'Found {total_profiles} employee profiles to normalize.')

        success_count = 0
        with transaction.atomic(): # Use a transaction to ensure all changes succeed or none do
            for i, profile in enumerate(profiles_to_process):
                user = profile.user
                self.stdout.write(f'({i+1}/{total_profiles}) Processing: {user.username}')

                # 1. Generate and set the new email
                new_email = generate_unique_employee_email(user.first_name, user.last_name)
                user.email = new_email
                self.stdout.write(f'  -> Setting email to: {new_email}')

                # 2. Invalidate the password
                user.set_unusable_password()
                self.stdout.write(f'  -> Invalidating password.')

                user.save()
                success_count += 1

        self.stdout.write(self.style.SUCCESS(f'\nNormalization complete! Successfully processed {success_count} employees.'))
