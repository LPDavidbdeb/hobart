from django.core.management.base import BaseCommand
from django.db import transaction
from address.functions import SimplifyPreserveTopology  # Corrected import
from address.models import FSA
from django.db.models import F

class Command(BaseCommand):
    help = 'Calculates and saves simplified boundaries for FSAs that are missing them.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tolerance',
            type=float,
            default=0.001,
            help='The tolerance for the simplification algorithm. Default is 0.001 (approx. 111 meters).',
        )
        parser.add_argument(
            '--force-update',
            action='store_true',
            help='Force update of all simplified boundaries, even if they already exist.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        tolerance = options['tolerance']
        force_update = options['force_update']
        
        self.stdout.write(self.style.SUCCESS(f"Starting simplification process with tolerance: {tolerance}"))

        # Build the queryset
        if force_update:
            queryset = FSA.objects.filter(boundary__isnull=False)
            self.stdout.write(self.style.WARNING("Forcing update for ALL FSAs with boundaries."))
        else:
            queryset = FSA.objects.filter(boundary__isnull=False, simplified_boundary__isnull=True)
            self.stdout.write("Processing only FSAs missing a simplified boundary.")

        # Annotate the queryset with the new simplified geometry
        # This does the heavy lifting in the database
        queryset = queryset.annotate(
            new_simplified_boundary=SimplifyPreserveTopology('boundary', tolerance)
        )

        # Update the objects in batches
        updated_count = 0
        for fsa in queryset.iterator():
            fsa.simplified_boundary = fsa.new_simplified_boundary
            fsa.save(update_fields=['simplified_boundary'])
            updated_count += 1
            if updated_count % 100 == 0:
                self.stdout.write(f"  ... processed {updated_count} FSAs ...")

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully updated {updated_count} simplified boundaries."))
        self.stdout.write(self.style.SUCCESS("Process Finished!"))
