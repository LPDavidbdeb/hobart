from django.core.management.base import BaseCommand
from organization.models import NestedTerritory

class Command(BaseCommand):
    help = "Verifies that each territory's boundary is spatially contained within its parent's boundary."

    def handle(self, *args, **options):
        self.stdout.write("Starting parent/child boundary containment check...")

        # Get all territories that have a boundary and a parent
        territories_to_check = NestedTerritory.objects.filter(
            boundary__isnull=False,
            parent__isnull=False
        ).select_related('parent')

        if not territories_to_check.exists():
            self.stdout.write(self.style.WARNING("No territories with boundaries and parents found to check."))
            return

        total_to_check = 0
        error_count = 0
        error_details = []

        for territory in territories_to_check.iterator():
            # We can only check if the parent also has a boundary
            if territory.parent and territory.parent.boundary:
                total_to_check += 1
                # The core check: is the child's geometry contained within the parent's geometry?
                if not territory.boundary.within(territory.parent.boundary):
                    error_count += 1
                    error_msg = (
                        f"FAILED: '{territory.name}' ({territory.get_type_display()}) is NOT within its parent "
                        f"'{territory.parent.name}' ({territory.parent.get_type_display()})."
                    )
                    self.stdout.write(self.style.ERROR(error_msg))
                    error_details.append(error_msg)

        self.stdout.write("\n" + "-"*50)
        self.stdout.write(self.style.SUCCESS("Verification Complete!"))
        self.stdout.write(f"- Checked {total_to_check} territories with boundaries against their parents.")

        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"- Found {error_count} containment errors."))
        else:
            self.stdout.write(self.style.SUCCESS("- All checked territories are correctly contained within their parents!"))
