import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef # Added Exists and OuterRef
#from django.contrib.gis.db.models.aggregates import GeoUnion # Still needed for other contexts, but not for GeoUnion
from django.contrib.gis.db.models import MultiPolygonField # Still needed for other contexts, but not for GeoUnion

from address.models import Address
from organization.models import NestedTerritory


class Command(BaseCommand):
    help = 'Evaluates the coverage of Region boundaries against geocoded addresses, province by province.'

    def handle(self, *args, **options):
        start_time = time.time()
        self.stdout.write(self.style.NOTICE("Starting territory coverage evaluation..."))

        provinces = NestedTerritory.objects.filter(type=NestedTerritory.TerritoryType.PROVINCE)
        if not provinces.exists():
            self.stdout.write(self.style.ERROR("No Province territories found. Please run 'build_base_hierarchy' first."))
            return

        total_addresses_in_db = Address.objects.filter(location__isnull=False).count()
        if total_addresses_in_db == 0:
            self.stdout.write(self.style.ERROR("No geocoded addresses found in the database to evaluate."))
            return

        self.stdout.write(f"Found {total_addresses_in_db} geocoded addresses to check.\n")

        grand_total = 0
        grand_total_covered = 0

        # Header for the report table
        self.stdout.write(f"{'Province':<25} | {'Total Addresses':>15} | {'Covered by Region':>20} | {'Gap (Uncovered)':>18} | {'Coverage':>10}")
        self.stdout.write("-" * 105)

        for province in provinces.order_by('name'):
            if not province.boundary:
                self.stdout.write(self.style.WARNING(f"Skipping province '{province.name}' due to missing boundary."))
                continue

            # Removed transaction.atomic() as it's not strictly necessary for read-only queries
            # and can sometimes add overhead.
            total_in_province = Address.objects.filter(location__intersects=province.boundary).count()
            grand_total += total_in_province

            if total_in_province == 0:
                # self.stdout.write(f"{province.name:<25} | {total_in_province:>15} | {0:>20} | {0:>18} | {0.00:9.2f}%")
                continue

            # This subquery will check, for each outer Address (referenced by 'OuterRef'),
            # if any Region in this province intersects its location.
            covering_region_exists = NestedTerritory.objects.filter(
                parent=province,
                type=NestedTerritory.TerritoryType.REGION,
                boundary__isnull=False,
                boundary__intersects=OuterRef('location') # Links to the Address.location
            )

            # Now, we get the count of addresses that are:
            # 1. Inside the province boundary
            # 2. Have at least one covering region (is_covered=True)
            covered_in_province = Address.objects.annotate(
                is_covered=Exists(covering_region_exists)
            ).filter(
                location__intersects=province.boundary,
                is_covered=True
            ).count()
                
            grand_total_covered += covered_in_province
            gap = total_in_province - covered_in_province
            coverage_pct = (covered_in_province / total_in_province * 100) if total_in_province > 0 else 0

            self.stdout.write(
                f"{province.name:<25} | {total_in_province:>15} | {covered_in_province:>20} | {gap:>18} | {coverage_pct:9.2f}%"
            )

        self.stdout.write("-" * 105)
        grand_gap = grand_total - grand_total_covered
        grand_coverage_pct = (grand_total_covered / grand_total * 100) if grand_total > 0 else 0
        self.stdout.write(self.style.SUCCESS(
            f"{'GRAND TOTAL':<25} | {grand_total:>15} | {grand_total_covered:>20} | {grand_gap:>18} | {grand_coverage_pct:9.2f}%"
        ))

        unaccounted_for = total_addresses_in_db - grand_total
        if unaccounted_for > 0:
            self.stdout.write(self.style.WARNING(f"\nNote: {unaccounted_for} addresses did not fall within any province boundary."))

        end_time = time.time()
        self.stdout.write(f"\nEvaluation finished in {end_time - start_time:.2f} seconds.")
