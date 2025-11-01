from django.core.management.base import BaseCommand
from organization.models import NestedTerritory

class Command(BaseCommand):
    help = "Verifies that ADDRESS nodes are spatially contained within their parent REGION's boundary."

    def handle(self, *args, **options):
        self.stdout.write("Starting spatial coherence check for REGION territories...")

        # Get all REGIONs that have a boundary defined
        regions_with_boundaries = NestedTerritory.objects.filter(
            type=NestedTerritory.TerritoryType.REGION,
            boundary__isnull=False
        ).prefetch_related('children')

        if not regions_with_boundaries.exists():
            self.stdout.write(self.style.WARNING("No REGION territories with boundaries found. Run import_census_divisions first."))
            return

        total_regions = regions_with_boundaries.count()
        self.stdout.write(f"Found {total_regions} regions with boundaries to check.")

        total_errors = 0

        for i, region in enumerate(regions_with_boundaries):
            self.stdout.write(f"\n({i+1}/{total_regions}) Checking Region: {region.name}")

            # Get all descendant addresses that have a location point
            descendant_addresses = region.get_descendants().filter(
                type=NestedTerritory.TerritoryType.ADDRESS,
                source_address__location__isnull=False
            )

            if not descendant_addresses.exists():
                self.stdout.write("  -> No descendant addresses with locations found. Skipping.")
                continue

            # Use a spatial query to find addresses whose location is NOT within the region's boundary
            # This is the core of the verification check
            outliers = descendant_addresses.exclude(
                source_address__location__within=region.boundary
            )

            outlier_count = outliers.count()
            total_addresses = descendant_addresses.count()

            if outlier_count > 0:
                self.stdout.write(self.style.ERROR(
                    f"  -> FOUND {outlier_count} / {total_addresses} addresses outside the boundary for '{region.name}'"
                ))
                total_errors += outlier_count
                # List the first few outliers for easy debugging
                for outlier_node in outliers[:5]:
                    self.stdout.write(f"    - Outlier: '{outlier_node.name}' (Address ID: {outlier_node.source_address.id})")
            else:
                self.stdout.write(self.style.SUCCESS(f"  -> OK! All {total_addresses} addresses are within the boundary."))

        self.stdout.write("\n" + "-"*50)
        if total_errors > 0:
            self.stdout.write(self.style.ERROR(f"Verification Complete: Found a total of {total_errors} outlier addresses."))
        else:
            self.stdout.write(self.style.SUCCESS("Verification Complete: All checked addresses are correctly contained within their region boundaries!"))
