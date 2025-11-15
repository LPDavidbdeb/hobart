from django.conf import settings
import decimal
import re # Import the regular expression module
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point

class FSA(gis_models.Model):
    """
    Represents a Forward Sortation Area (FSA), the first three characters of a Canadian postal code.
    This model is designed to store geographic boundary data from Statistics Canada's
    Census Forward Sortation Area Boundary File.
    """
    class Source(gis_models.TextChoices):
        CENSUS = 'CENSUS', 'From Statistics Canada Census'
        INFERRED = 'INFERRED', 'Inferred from Client Data'

    class BoundaryType(gis_models.TextChoices):
        OFFICIAL = 'OFFICIAL', 'Official Census Boundary'
        INFERRED_CONVEX_HULL = 'INFERRED_CONVEX_HULL', 'Inferred from Client Points (Convex Hull)'

    code = gis_models.CharField(max_length=3, unique=True, db_index=True, help_text="The 3-character Forward Sortation Area code (e.g., H2X).")
    cfsa_uid = gis_models.CharField(max_length=21, unique=True, null=True, blank=True, db_index=True, help_text="Census Forward Sortation Area Unique Identifier (CFSAUID), which is the IDUGD.")
    pruid = gis_models.CharField(max_length=2, db_index=True, null=True, blank=True, help_text="Unique identifier for the province or territory (PRUID).")
    land_area = gis_models.FloatField(null=True, blank=True, help_text="Land area in square kilometers.")
    boundary = gis_models.MultiPolygonField(srid=4326, null=True, blank=True, help_text="The geographic boundary of the FSA.")
    simplified_boundary = gis_models.MultiPolygonField(srid=4326, null=True, blank=True, help_text="A pre-calculated, low-resolution version of the boundary for fast map rendering.")
    center_point = gis_models.PointField(srid=4326, null=True, blank=True, help_text="The geographic center (centroid) of the FSA, often from a geocoding service.")
    census_year = gis_models.PositiveIntegerField(null=True, blank=True, db_index=True, help_text="The census year the data is from (e.g., 2021).")
    description = gis_models.CharField(max_length=255, blank=True, help_text="A description for this FSA, which may be imported from external sources.")
    client_count = gis_models.PositiveIntegerField(default=0, editable=False, help_text="Total number of active clients in this FSA.")
    source = gis_models.CharField(max_length=20, choices=Source.choices, default=Source.CENSUS, db_index=True)
    boundary_type = gis_models.CharField(max_length=30, choices=BoundaryType.choices, null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "Forward Sortation Area (FSA)"
        verbose_name_plural = "Forward Sortation Areas (FSAs)"
        ordering = ['code']
        app_label = 'address'

    def __str__(self):
        return self.code

class PostalCode(gis_models.Model):
    """
    Represents a 6-character Canadian postal code and its geocoded location.
    """
    code = gis_models.CharField(max_length=7, unique=True, db_index=True, help_text="The 6 or 7-character postal code (e.g., H2X1X6).")
    latitude = gis_models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = gis_models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location = gis_models.PointField(null=True, blank=True, srid=4326, help_text="The geocoded point for this postal code.")
    last_geocoded = gis_models.DateTimeField(null=True, blank=True, help_text="When the postal code was last geocoded.")

    class Meta:
        verbose_name = "Postal Code"
        verbose_name_plural = "Postal Codes"
        ordering = ['code']
        app_label = 'address'

    def __str__(self):
        return self.code

class AddressStatus(gis_models.Model):
    name = gis_models.CharField(max_length=50, unique=True)
    description = gis_models.TextField(blank=True)
    badge_class = gis_models.CharField(max_length=50, default='bg-secondary', help_text="Bootstrap badge class, e.g., 'bg-success', 'bg-warning text-dark', 'bg-danger'.")

    class Meta:
        verbose_name = "Address Status"
        verbose_name_plural = "Address Statuses"
        app_label = 'address'

    def __str__informed_consent_text(self):
        return self.name

class AddressValidationLog(gis_models.Model):
    timestamp = gis_models.DateTimeField(auto_now_add=True)
    run_by = gis_models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=gis_models.SET_NULL, null=True, blank=True)
    clients_complete = gis_models.PositiveIntegerField(default=0)
    clients_incomplete = gis_models.PositiveIntegerField(default=0)
    clients_missing = gis_models.PositiveIntegerField(default=0)
    employees_complete = gis_models.PositiveIntegerField(default=0)
    employees_incomplete = gis_models.PositiveIntegerField(default=0)
    employees_missing = gis_models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Address Validation Log"
        verbose_name_plural = "Address Validation Logs"
        app_label = 'address'

    def __str__(self):
        return f"Validation run at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

class Address(gis_models.Model):
    """
    Stores a rich, structured address, abstracting Google's complexity.
    """
    # --- Core Fields ---
    formatted = gis_models.CharField(max_length=255, blank=True, null=True)
    place_id = gis_models.CharField(max_length=255, unique=True, null=True, blank=True)
    latitude = gis_models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = gis_models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    raw_response = gis_models.JSONField(null=True, blank=True)

    # New PostGIS PointField
    location = gis_models.PointField(null=True, blank=True, srid=4326)

    territories = gis_models.ManyToManyField(
        'organization.NestedTerritory',
        blank=True,
        related_name="addresses",
        help_text="Links this address to all relevant territory nodes (e.g., its Postal Code, its FED, its City)."
    )

    # --- Standardized Properties (Abstraction Layer) ---
    def get_component(self, component_type, fallback_types=None):
        if not self.raw_response or 'address_components' not in self.raw_response:
            return None
        
        types_to_check = [component_type]
        if fallback_types:
            types_to_check.extend(fallback_types)

        for comp_type in types_to_check:
            for component in self.raw_response['address_components']:
                if comp_type in component.get('types', []):
                    return component.get('long_name')
        return None

    @property
    def street_number(self):
        return self.get_component('street_number')

    @property
    def route(self):
        return self.get_component('route')

    @property
    def city(self):
        return self.get_component('locality', fallback_types=['administrative_area_level_3', 'sublocality'])

    @property
    def province(self):
        return self.get_component('administrative_area_level_1')

    @property
    def postal_code(self):
        """
        Finds the postal code from the address components and validates its format.
        Returns a valid 6 or 7 character Canadian postal code, or None.
        """
        code = self.get_component('postal_code')
        if not code:
            return None
        
        # Regex to match a Canadian postal code format (e.g., A1A 1A1 or A1A1A1)
        # It's flexible about the space.
        match = re.search(r'^[A-Z]\d[A-Z][ -]?\d[A-Z]\d$', code.upper())
        
        if match:
            return match.group(0).replace(' ', '') # Return the standardized 6-character code
        return None

    def is_degenerate(self):
        """
        Checks if the address is missing critical components. A postal code is now checked for validity.
        """
        # The postal_code property now returns None if it's invalid, so this check is simpler.
        return not self.street_number or not self.route or not self.city or not self.postal_code

    def get_degeneracy_reasons(self):
        reasons = []
        if not self.street_number: reasons.append('Street Number')
        if not self.route: reasons.append('Street Name')
        if not self.city: reasons.append('City/Locality')
        if not self.postal_code: reasons.append('Valid Postal Code') # Updated reason
        return reasons

    @classmethod
    def save_from_google_maps_data(cls, data):
        if not data or not data.get('place_id'):
            return None, False

        defaults = {
            'formatted': data.get('formatted_address'),
            'latitude': decimal.Decimal(data['geometry']['location']['lat']),
            'longitude': decimal.Decimal(data['geometry']['location']['lng']),
            'raw_response': data,
        }

        lat = data['geometry']['location']['lat']
        lng = data['geometry']['location']['lng']
        if lat is not None and lng is not None:
            defaults['location'] = Point(float(lng), float(lat), srid=4326)

        address, created = cls.objects.update_or_create(place_id=data['place_id'], defaults=defaults)
        return address, created

    def __str__(self):
        return self.formatted or self.place_id or "Unresolved address"

    class Meta:
        app_label = 'address'
