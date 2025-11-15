from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from employees.models import EmployeeProfile

class Command(BaseCommand):
    help = 'Finds technician profiles that still have FSA assignments after the employee was promoted to Manager.'

    def _get_manager_profile(self, technician_profile):
        """
        If a duplicate Manager profile exists for the same person, returns it. 
        Otherwise, returns None.
        """
        user = technician_profile.user
        # Find other user accounts with the same first/last name.
        duplicate_users = User.objects.filter(
            first_name__iexact=user.first_name,
            last_name__iexact=user.last_name
        ).exclude(pk=user.pk)

        if not duplicate_users.exists():
            return None
        
        # Check if any of the duplicate users have a manager profile.
        return EmployeeProfile.objects.filter(
            user__in=duplicate_users,
            role=EmployeeProfile.Role.MANAGER
        ).first()

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO("--- Checking for Obsolete Technician Profiles with Active FSAs ---"))

        # Get all technicians who have at least one FSA assigned.
        technicians_with_fsas = EmployeeProfile.objects.filter(
            role=EmployeeProfile.Role.TECHNICIAN,
            responsible_fsas__isnull=False
        ).distinct()

        problem_found = False
        for tech_profile in technicians_with_fsas:
            # For each technician, check if they have been promoted.
            manager_profile = self._get_manager_profile(tech_profile)
            
            if manager_profile:
                problem_found = True
                fsa_count = tech_profile.responsible_fsas.count()
                fsa_list = ", ".join(tech_profile.responsible_fsas.all()[:5].values_list('code', flat=True))
                if fsa_count > 5:
                    fsa_list += f", and {fsa_count - 5} more..."

                self.stdout.write(self.style.ERROR(
                    f"\n- CONFLICT: Promoted employee '{tech_profile.user.get_full_name()}' has an obsolete technician profile that needs cleanup."
                ))
                self.stdout.write(f"  - Obsolete Technician Profile ID: {tech_profile.id} (User: {tech_profile.user.username})")
                self.stdout.write(f"  - Correct Manager Profile ID: {manager_profile.id} (User: {manager_profile.user.username})")
                self.stdout.write(self.style.WARNING(f"  - This obsolete profile is still assigned to {fsa_count} FSAs: [{fsa_list}]"))

        if not problem_found:
            self.stdout.write(self.style.SUCCESS("No instances found of promoted managers with lingering technician FSA assignments."))

        self.stdout.write(self.style.HTTP_INFO("\n--- Script Finished ---"))
