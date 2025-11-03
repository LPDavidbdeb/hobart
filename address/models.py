from django.conf import settings
import decimal
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import Point
# from organization.models import NestedTerritory # <-- 1. REMOVED this import

class FSA(gis_models.Model):
    """
    Represents a Forward Sortation Area (FSA), the first three characters of a Canadian postal code.
    This model is designed to store geographic boundary data from Statistics Canada's
    Census Forward Sortation Area Boundary File.
    """
    code = gis_models.CharField(max_length=3, unique=True, db_index=True, help_text="The 3-character Forward Sortation Area code (e.g., H2X).")
    cfsa_uid = gis_models.CharField(max_length=10, unique=True, null=True, blank=True, db_index=True, help_text="Census Forward Sortation Area Unique Identifier (CFSAUID).")
    pruid = gis_models.CharField(max_length=4, db_index=True, null=True, blank=True, help_text="Unique identifier for the province or territory (PRUID).")
    land_area = gis_models.FloatField(null=True, blank=True, help_text="Land area in square kilometers.")
    boundary = gis_models.MultiPolygonField(srid=4326, null=True, blank=True, help_text="The geographic boundary of the FSA.")
    census_year = gis_models.PositiveIntegerField(null=True, blank=True, db_index=True, help_text="The census year the data is from (e.g., 2021).")
    description = gis_models.CharField(max_length=255, blank=True, help_text="A description for this FSA, which may be imported from external sources.")

    class Meta:
        verbose_name = "Forward Sortation Area (FSA)"
        verbose_name_plural = "Forward Sortation Areas (FSAs)"
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
        'organization.NestedTerritory', # <-- 2. Used a string here
        blank=True,
        related_name="addresses",
        help_text="Links this address to all relevant territory nodes (e.g., its Postal Code, its FED, its City)."
    )

    # --- Standardized Properties (Abstraction Layer) ---
    def get_component(self, component_type, fallback_types=None):
        """
        Intelligently searches for a component in the raw_response JSON.
        `component_type` is the desired type (e.g., 'locality').
        `fallback_types` is an optional list of other types to try in order.
        """
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
        return self.get_component('postal_code')

    def is_degenerate(self):
        """
        Checks if the address is missing critical components using the intelligent properties.
        A postal code is considered degenerate if it's missing or less than 6 characters.
        """
        return not self.street_number or not self.route or not self.city or not self.postal_code or len(self.postal_code) < 6

    def get_degeneracy_reasons(self):
        """
        Returns a list of human-readable reasons for why the address is degenerate.
        """
        reasons = []
        if not self.street_number: reasons.append('Street Number')
        if not self.route: reasons.append('Street Name')
        if not self.city: reasons.append('City/Locality')
        if not self.postal_code or len(self.postal_code) < 6: reasons.append('Postal Code')
        return reasons

    @classmethod
    def save_from_google_maps_data(cls, data):
        if not data or not data.get('place_id'):
            return None, False

        defaults = {
            'formatted': data.get('formatted_address'),
            'latitude': decimal.Decimal(data['geometry']['location']['lat']),
            'longitude': decimal.Decimal(data['geometry']['location']['lng']),
            'raw_response': data, # Store the entire response
        }

        # Populate the new location PointField
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
