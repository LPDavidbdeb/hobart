import time
from django.core.management.base import BaseCommand
from django.db.models import F, FloatField
from django.contrib.gis.db.models.aggregates import Union # Corrected import: Union from aggregates
from django.contrib.gis.db.models.functions import Area, Transform
from django.db.models.functions import Cast

from organization.models import NestedTerritory

# Statistics Canada Lambert Projection (meters)
# This is an equal-area projection, perfect for calculating area in Canada.
CANADA_LAMBERT_SRID = 3347

class Command(BaseCommand):
    help = 'Validates the spatial coverage of Regions within their parent Provinces.'

    def handle(self, *args, **options):
        start_time = time.time()
        self.stdout.write(self.style.NOTICE("Starting spatial coverage validation (using database)..."))

        provinces = NestedTerritory.objects.filter(
            type=NestedTerritory.TerritoryType.PROVINCE
        ).order_by('name')

        if not provinces.exists():
            self.stdout.write(self.style.ERROR("No Province territories found in the database. Please run 'build_base_hierarchy' first."))
            return

        self.stdout.write(f"\n{'Province':<25} | {'Province Area (sq km)':>20} | {'Regions Area (sq km)':>20} | {'Coverage':>10}")
        self.stdout.write("-" * 90)

        for province in provinces:
            if not province.boundary:
                self.stdout.write(self.style.WARNING(f"{province.name:<25} | {'N/A (Missing Boundary)':>20} | {'N/A':>20} | {'N/A':>10}"))
                continue

            # 1. Get the province's area, calculated correctly
            prov_data = NestedTerritory.objects.filter(pk=province.pk).annotate(
                # Transform to the equal-area projection, then get area in meters
                area_m2=Area(Transform('boundary', CANADA_LAMBERT_SRID))
            ).first()
            
            # Handle potential null/empty geometries
            if not prov_data or not prov_data.area_m2:
                self.stdout.write(self.style.WARNING(f"{province.name:<25} | {'0.00 (Empty Geometry)':>20} | {'N/A':>20} | {'N/A':>10}"))
                continue
                
            prov_area_sq_km = prov_data.area_m2.sq_m / 1000000.0

            # 2. Get the union of all child regions' areas
            regions_in_prov = NestedTerritory.objects.filter(
                parent=province,
                type=NestedTerritory.TerritoryType.REGION,
                boundary__isnull=False
            )

            regions_union_area_sq_km = 0.0
            if regions_in_prov.exists():
                # Let PostGIS do all the hard work in the correct order:
                # 1. Transform each region's boundary to SRID 3347
                # 2. Union all the *transformed* boundaries
                # 3. Calculate the area of the *final union*
                regions_union_data = regions_in_prov.aggregate(
                    total_area_m2=Area(
                        Union(
                            Transform('boundary', CANADA_LAMBERT_SRID)
                        )
                    )
                )
                
                # Check if aggregation returned a valid area
                if regions_union_data['total_area_m2']:
                    regions_union_area_sq_km = regions_union_data['total_area_m2'].sq_m / 1000000.0

            # 3. Calculate coverage and print the report row
            coverage_pct = (regions_union_area_sq_km / prov_area_sq_km * 100) if prov_area_sq_km > 0 else 0

            self.stdout.write(
                f"{province.name:<25} | {prov_area_sq_km:>20.2f} | {regions_union_area_sq_km:>20.2f} | {coverage_pct:9.2f}%"
            )

        self.stdout.write("-" * 90)
        end_time = time.time()
        self.stdout.write(self.style.SUCCESS(f"\nDatabase validation finished in {end_time - start_time:.2f} seconds!"))
