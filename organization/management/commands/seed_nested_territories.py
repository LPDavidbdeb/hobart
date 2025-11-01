import time
import unicodedata
import re
import decimal
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point

from address.models import Address
from organization.models import NestedTerritory
from organization.signals import update_nested_territory_on_address_save
from DAO.adresses_DAO import GoogleMapsClient


class Command(BaseCommand):
    help = 'Builds the hierarchical NestedTerritory tree efficiently from shapefiles and links addresses.'

    def add_arguments(self, parser):
        parser.add_argument('province_shapefile', type=str, help='Path to the province/state .shp file.')
        parser.add_argument('region_shapefile', type=str, help='Path to the census division .shp file.')
        parser.add_argument('--region-name-field', default='DRNOM', help='Shapefile field for the region name.')
        parser.add_argument('--region-code-field', default='DRIDU', help='Shapefile field for the unique region ID.')

    def _normalize(self, name):
        if not name: return ''
        return unicodedata.normalize('NFKD', str(name).lower()).encode('ascii', 'ignore').decode('utf-8').strip()

    def _ensure_multipolygon_4326(self, gdal_geom):
        if gdal_geom.srid != 4326:
            gdal_geom.transform(4326)
        geos_geom = GEOSGeometry(gdal_geom.wkt, srid=4326)
        if geos_geom.geom_type == 'Polygon':
            return MultiPolygon(geos_geom)
        if geos_geom.geom_type == 'MultiPolygon':
            return geos_geom
        raise TypeError(f"Unsupported geometry type: {geos_geom.geom_type}")

    # This function is now commented out in handle() to prevent API calls during testing.
    # def _geocode_and_fix_addresses(self):
    #     self.stdout.write(self.style.NOTICE("  -> Starting API geocoding to fix inconsistent or degenerate addresses..."))
    #     gmaps = GoogleMapsClient()
        
    #     all_addresses = list(Address.objects.all())
    #     addresses_to_fix = [addr for addr in all_addresses if addr.is_degenerate()]
        
    #     total_to_fix = len(addresses_to_fix)
    #     self.stdout.write(f"  -> Found {total_to_fix} degenerate addresses to fix via API.")

    #     if total_to_fix == 0:
    #         self.stdout.write(self.style.SUCCESS("  -> No addresses needed fixing."))
    #         return

    #     fixed_count = 0
    #     failed_count = 0
        
    #     for i, addr in enumerate(addresses_to_fix):
    #         address_string = addr.formatted
    #         if not address_string or not address_string.strip():
    #             failed_count += 1
    #             continue

    #         if i > 0 and i % 40 == 0:
    #             time.sleep(1)

    #         results = gmaps.geocode(address_string)
    #         if results:
    #             address_obj, created = Address.save_from_google_maps_data(results[0])
    #             if address_obj and not address_obj.is_degenerate():
    #                 fixed_count += 1
    #             else:
    #                 failed_count += 1
    #         else:
    #             failed_count += 1
            
    #         if (i + 1) % 100 == 0 or (i + 1) == total_to_fix:
    #             self.stdout.write(f"    ... processed {i + 1}/{total_to_fix} (Fixed: {fixed_count}, Failed: {failed_count})")

    #     self.stdout.write(self.style.SUCCESS(f"  -> API fixing complete. Fixed: {fixed_count}, Failed: {failed_count}"))

    def handle(self, *args, **options):
        # FIXED: Disconnect the post_save signal to prevent it from running during the script
        post_save.disconnect(update_nested_territory_on_address_save, sender=Address)
        self.stdout.write(self.style.WARNING("Temporarily disconnected the Address post-save signal."))

        start_time = time.time()

        try:
            self.stdout.write(self.style.WARNING("This is a destructive operation..."))
            if input("Are you sure? (y/n): ").lower() != 'y':
                self.stdout.write(self.style.ERROR("Operation cancelled."))
                return

            try:
                NestedTerritory.objects.disable_mptt_updates()
                self.stdout.write(self.style.NOTICE("MPTT updates disabled."))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not disable MPTT updates: {e}."))

            # Step 1/5
            self.stdout.write(self.style.WARNING("Step 1/5: Clearing old data..."))
            with transaction.atomic():
                self.stdout.write("  -> Nullifying address links...")
                updated_count = 1
                while updated_count > 0:
                    pks = list(Address.objects.filter(postal_code_node__isnull=False).values_list('pk', flat=True)[:5000])
                    if not pks:
                        break
                    updated_count = Address.objects.filter(pk__in=pks).update(postal_code_node=None)
                
                self.stdout.write("  -> Deleting territory tree...")
                NestedTerritory.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("  -> Complete."))

            # Step 2/5
            self.stdout.write(self.style.SUCCESS("Step 2/5: Loading Provinces and Regions..."))
            with transaction.atomic():
                self._load_provinces_and_regions(options)
            self.stdout.write(self.style.SUCCESS("  -> Complete."))

            # Step 3/5 (API calls disabled for testing)
            # self.stdout.write(self.style.SUCCESS("Step 3/5: Geocoding and fixing degenerate addresses..."))
            # self._geocode_and_fix_addresses()
            # self.stdout.write(self.style.SUCCESS("  -> Complete."))
            self.stdout.write(self.style.WARNING("Step 3/5: Geocoding and fixing degenerate addresses (SKIPPED for testing)."))

            # Step 4/5
            self.stdout.write(self.style.SUCCESS("Step 4/5: Placing addresses and building lower tree..."))
            self._place_addresses_optimized()
            self.stdout.write(self.style.SUCCESS("  -> Complete."))

            # Step 5/5
            self.stdout.write(self.style.SUCCESS("Step 5/5: Finalizing tree structure..."))
            try:
                NestedTerritory.objects.enable_mptt_updates()
                self.stdout.write(self.style.NOTICE("  -> MPTT updates re-enabled."))
            except Exception as e:
                 self.stdout.write(self.style.WARNING(f"Could not re-enable MPTT updates: {e}."))
                 
            NestedTerritory.objects.rebuild()
            self.stdout.write(self.style.NOTICE("  -> MPTT tree rebuilt. Run 'update_client_counts' separately."))

            end_time = time.time()
            self.stdout.write(self.style.SUCCESS(f"\nProcess Finished in {end_time - start_time:.2f} seconds!"))

        finally:
            # FIXED: Reconnect the signal in a finally block to ensure it always runs
            post_save.connect(update_nested_territory_on_address_save, sender=Address)
            self.stdout.write(self.style.SUCCESS("Reconnected the Address post-save signal."))


    def _load_provinces_and_regions(self, options):
        root_node = NestedTerritory.objects.create(name='Canada', type=NestedTerritory.TerritoryType.COUNTRY)
        
        prov_ds = DataSource(options['province_shapefile'])
        try:
            prov_ds[0].layer.SetAttributeFilter("admin = 'Canada'")
            prov_features = prov_ds[0]
        except Exception:
            prov_features = [f for f in prov_ds[0] if f.get('admin') == 'Canada']

        prov_nodes = [
            NestedTerritory(
                name=f.get('name'), type=NestedTerritory.TerritoryType.PROVINCE, parent=root_node,
                boundary=self._ensure_multipolygon_4326(f.geom),
                code=f.get('iso_3166_2').split('-')[-1]
            )
            for f in prov_features
        ]
        NestedTerritory.objects.bulk_create(prov_nodes)
        self.stdout.write(f"  -> Created {len(prov_nodes)} province nodes.")

        region_ds = DataSource(options['region_shapefile'])
        region_nodes_map = {}
        for feature in region_ds[0]:
            geom = self._ensure_multipolygon_4326(feature.geom)
            
            parent = NestedTerritory.objects.filter(
                type=NestedTerritory.TerritoryType.PROVINCE,
                boundary__contains=geom.centroid
            ).first()
            
            if parent:
                name = feature.get(options['region_name_field'])
                key = (parent.id, name)
                if key not in region_nodes_map:
                    region_nodes_map[key] = NestedTerritory(
                        name=name, type=NestedTerritory.TerritoryType.REGION, parent=parent,
                        boundary=geom, code=feature.get(options['region_code_field'])
                    )
        NestedTerritory.objects.bulk_create(list(region_nodes_map.values()))
        self.stdout.write(f"  -> Created {len(region_nodes_map)} region nodes.")

    def _build_lower_tree_for_addresses(self, addresses, parent_node):
        pc_regex = re.compile(r'[^a-z0-9]')
        # This map holds all data: {city_name: {fsa_code: {pc_code: True}}} (nested defaultdicts)
        cities_map = defaultdict(lambda: defaultdict(lambda: defaultdict(dict))) 

        # 1. Build the in-memory map of all addresses
        for addr in addresses:
            city_name = self._normalize(addr.city) or 'unknown_city'
            if not addr.postal_code: continue
            pc = pc_regex.sub('', str(addr.postal_code).lower())
            if len(pc) < 3: continue
            cities_map[city_name][pc[:3]][pc] = True
        
        # 2. --- Handle CITIES ---
        city_names_to_create = set(cities_map.keys())
        city_inserts = [
            NestedTerritory(name=name, type=NestedTerritory.TerritoryType.CITY, parent=parent_node)
            for name in city_names_to_create
        ]
        NestedTerritory.objects.bulk_create(city_inserts, batch_size=2000, ignore_conflicts=True)
        
        # Re-fetch ALL relevant cities (new and existing) to get objects with PKs
        city_obj_map = {
            c.name: c 
            for c in NestedTerritory.objects.filter(
                parent=parent_node,
                type=NestedTerritory.TerritoryType.CITY,
                name__in=city_names_to_create
            )
        }

        # 3. --- Handle FSAs (Forward Sortation Areas) ---
        fsa_inserts = []
        fsa_names_to_create = set()
        parent_id_to_fsa_names = defaultdict(set) # To help re-fetch FSAs by their parent

        for city_name, fsa_codes_map in cities_map.items(): # fsa_codes_map is defaultdict(dict) for fsa_code -> pc_code
            city_obj = city_obj_map.get(city_name)
            if not city_obj: continue

            for fsa_code in fsa_codes_map.keys():
                fsa_inserts.append(NestedTerritory(name=fsa_code, type=NestedTerritory.TerritoryType.FSA, parent=city_obj))
                fsa_names_to_create.add(fsa_code)
                parent_id_to_fsa_names[city_obj.id].add(fsa_code)
        
        NestedTerritory.objects.bulk_create(fsa_inserts, batch_size=2000, ignore_conflicts=True)

        # Re-fetch ALL relevant FSAs (new and existing) to get objects with PKs
        relevant_city_ids = list(parent_id_to_fsa_names.keys())
        fsa_obj_map = {}
        if relevant_city_ids: # Only query if there are cities to look for
            fsa_qs = NestedTerritory.objects.filter(
                parent_id__in=relevant_city_ids,
                type=NestedTerritory.TerritoryType.FSA,
                name__in=fsa_names_to_create
            ).select_related('parent') # select_related('parent') gets the city object

            for fsa in fsa_qs:
                # Ensure this FSA belongs to the city we think it does
                if fsa.name in parent_id_to_fsa_names.get(fsa.parent_id, set()):
                    key = (fsa.parent.name, fsa.name) # Use parent's name for the key
                    fsa_obj_map[key] = fsa

        # 4. --- Handle POSTAL CODES ---
        pc_inserts = []
        pc_names_to_create = set()
        parent_id_to_pc_names = defaultdict(set) # To help re-fetch PCs by their parent

        for city_name, fsa_codes_map in cities_map.items():
            for fsa_code, pc_codes_map in fsa_codes_map.items(): # pc_codes_map is defaultdict(dict) for pc_code -> True
                fsa_obj = fsa_obj_map.get((city_name, fsa_code))
                if not fsa_obj: continue

                for pc_name in pc_codes_map.keys(): # pc_name is the actual postal code
                    pc_inserts.append(NestedTerritory(name=pc_name, type=NestedTerritory.TerritoryType.POSTAL_CODE, parent=fsa_obj))
                    pc_names_to_create.add(pc_name)
                    parent_id_to_pc_names[fsa_obj.id].add(pc_name)

        NestedTerritory.objects.bulk_create(pc_inserts, batch_size=2000, ignore_conflicts=True)

        # Re-fetch ALL relevant PCs (new and existing) to get objects with PKs
        relevant_fsa_ids = list(parent_id_to_pc_names.keys())
        pc_obj_map = {}
        if relevant_fsa_ids: # Only query if there are FSAs to look for
            pc_qs = NestedTerritory.objects.filter(
                parent_id__in=relevant_fsa_ids,
                type=NestedTerritory.TerritoryType.POSTAL_CODE,
                name__in=pc_names_to_create
            ).select_related('parent', 'parent__parent') # parent=FSA, parent__parent=City

            for pc in pc_qs:
                if pc.name in parent_id_to_pc_names.get(pc.parent_id, set()):
                    # Reconstruct the key using parent names
                    city_name = pc.parent.parent.name if pc.parent and pc.parent.parent else None
                    fsa_name = pc.parent.name if pc.parent else None
                    if city_name and fsa_name:
                        key = (city_name, fsa_name, pc.name)
                        pc_obj_map[key] = pc

        # 5. --- Link Addresses to Postal Code nodes ---
        addresses_to_update = []
        for addr_data in addresses:
            city_name = self._normalize(addr_data.city) or 'unknown_city'
            if not addr_data.postal_code: continue
            pc_full = pc_regex.sub('', str(addr_data.postal_code).lower())
            if len(pc_full) < 3: continue
            fsa_code = pc_full[:3]
            
            # Find the fully-pathed PC node
            pc_node = pc_obj_map.get((city_name, fsa_code, pc_full))
            if pc_node:
                addr_data.postal_code_node = pc_node
                addresses_to_update.append(addr_data)
        
        if addresses_to_update:
            Address.objects.bulk_update(addresses_to_update, ['postal_code_node'], batch_size=5000)
            
        return len(addresses_to_update)

    def _place_addresses_optimized(self):
        self.stdout.write(self.style.NOTICE("  -> Starting Primary Pass (placing by region)..."))
        regions = list(NestedTerritory.objects.filter(type=NestedTerritory.TerritoryType.REGION).only('id', 'name', 'boundary'))
        total_placed_primary = 0

        for i, region in enumerate(regions, 1):
            if not region.boundary:
                self.stdout.write(self.style.WARNING(f"    Skipping region '{region.name}' due to missing boundary."))
                continue

            with transaction.atomic():
                addresses_in_region_qs = Address.objects.filter(
                    location__intersects=region.boundary, 
                    location__isnull=False,
                    postal_code_node__isnull=True
                )
                addresses_in_region = [addr for addr in addresses_in_region_qs if not addr.is_degenerate()]

                if not addresses_in_region:
                    continue
                
                self.stdout.write(f"    ({i}/{len(regions)}) Processing {region.name}: Found {len(addresses_in_region)} complete addresses.")
                placed_count = self._build_lower_tree_for_addresses(addresses_in_region, region)
                total_placed_primary += placed_count

        self.stdout.write(self.style.SUCCESS(f"  -> Primary Pass Complete. Placed {total_placed_primary} addresses."))

        self.stdout.write(self.style.NOTICE("  -> Starting Fallback Pass (placing by province)..."))
        provinces = list(NestedTerritory.objects.filter(type=NestedTerritory.TerritoryType.PROVINCE).only('id', 'name', 'boundary'))
        total_placed_fallback = 0

        for i, province in enumerate(provinces, 1):
            if not province.boundary:
                self.stdout.write(self.style.WARNING(f"    Skipping province '{province.name}' due to missing boundary."))
                continue

            with transaction.atomic():
                addresses_in_province_qs = Address.objects.filter(
                    location__intersects=province.boundary, 
                    location__isnull=False, 
                    postal_code_node__isnull=True
                )
                addresses_in_province = [addr for addr in addresses_in_province_qs if not addr.is_degenerate()]

                if not addresses_in_province:
                    continue

                self.stdout.write(f"    ({i}/{len(provinces)}) Processing {province.name}: Found {len(addresses_in_province)} fallback addresses.")
                placed_count = self._build_lower_tree_for_addresses(addresses_in_province, province)
                total_placed_fallback += placed_count

        self.stdout.write(self.style.SUCCESS(f"  -> Fallback Pass Complete. Placed {total_placed_fallback} addresses."))
        
        total_placed = total_placed_primary + total_placed_fallback
        total_possible = Address.objects.exclude(location__isnull=True).count()
        self.stdout.write(f"\nTotal Placed: {total_placed} / {total_possible}.")
        unplaced_count = total_possible - total_placed
        if unplaced_count > 0:
            self.stdout.write(self.style.WARNING(f"Could not place {unplaced_count} addresses (likely degenerate or outside all province boundaries)."))
