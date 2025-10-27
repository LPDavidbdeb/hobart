from django.db import models
from django.conf import settings
import decimal

class FSA(models.Model):
    # ... (FSA model remains the same)
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="The unique code for this FSA.")
    description = models.CharField(max_length=255, blank=True, help_text="A description for this FSA (e.g., city/region).")

    class Meta:
        verbose_name = "FSA"
        verbose_name_plural = "FSAs"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.description}" if self.description else self.code

class AddressStatus(models.Model):
    # ... (AddressStatus model remains the same)
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    badge_class = models.CharField(max_length=50, default='bg-secondary', help_text="Bootstrap badge class, e.g., 'bg-success', 'bg-warning text-dark', 'bg-danger'.")

    class Meta:
        verbose_name = "Address Status"
        verbose_name_plural = "Address Statuses"

    def __str__(self):
        return self.name

class AddressValidationLog(models.Model):
    # ... (AddressValidationLog model remains the same)
    timestamp = models.DateTimeField(auto_now_add=True)
    run_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    clients_complete = models.PositiveIntegerField(default=0)
    clients_incomplete = models.PositiveIntegerField(default=0)
    clients_missing = models.PositiveIntegerField(default=0)
    employees_complete = models.PositiveIntegerField(default=0)
    employees_incomplete = models.PositiveIntegerField(default=0)
    employees_missing = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Address Validation Log"
        verbose_name_plural = "Address Validation Logs"

    def __str__(self):
        return f"Validation run at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

class Address(models.Model):
    """
    Stores a rich, structured address, abstracting Google's complexity.
    """
    # --- Raw Component Fields ---
    formatted = models.CharField(max_length=255, blank=True, null=True)
    place_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    street_number = models.CharField(max_length=50, blank=True, null=True)
    route = models.CharField(max_length=100, blank=True, null=True)  # Street name
    locality = models.CharField(max_length=100, blank=True, null=True)  # Official city name
    sublocality = models.CharField(max_length=100, blank=True, null=True) # Borough or neighborhood
    administrative_area_level_3 = models.CharField(max_length=100, blank=True, null=True) # e.g., Leamington
    administrative_area_level_2 = models.CharField(max_length=100, blank=True, null=True) # County, e.g., Essex County
    administrative_area_level_1 = models.CharField(max_length=100, blank=True, null=True)  # Province/State, e.g., ON
    country = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    raw_response = models.JSONField(null=True, blank=True)

    # --- Standardized Properties (Abstraction Layer) ---
    @property
    def city(self):
        """Intelligently determines the city name from available fields."""
        return self.locality or self.administrative_area_level_3 or self.sublocality

    @property
    def province(self):
        """Returns the province/state."""
        return self.administrative_area_level_1

    @property
    def street_address(self):
        """Returns the street number and name, if available."""
        return f"{self.street_number} {self.route}" if self.street_number and self.route else ""

    def is_degenerate(self):
        """Checks if the address is missing critical components using the standardized properties."""
        return not self.street_number or not self.route or not self.city or not self.postal_code or len(self.postal_code) < 6

    def get_degeneracy_reasons(self):
        """Returns a list of human-readable reasons for why the address is degenerate."""
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

        address_components = {comp['types'][0]: comp['long_name'] for comp in data.get('address_components', []) if comp.get('types')}

        defaults = {
            'formatted': data.get('formatted_address'),
            'latitude': decimal.Decimal(data['geometry']['location']['lat']),
            'longitude': decimal.Decimal(data['geometry']['location']['lng']),
            'street_number': address_components.get('street_number'),
            'route': address_components.get('route'),
            'locality': address_components.get('locality'),
            'sublocality': address_components.get('sublocality'),
            'administrative_area_level_3': address_components.get('administrative_area_level_3'),
            'administrative_area_level_2': address_components.get('administrative_area_level_2'),
            'administrative_area_level_1': address_components.get('administrative_area_level_1'),
            'country': address_components.get('country'),
            'postal_code': address_components.get('postal_code'),
            'raw_response': data,
        }

        address, created = cls.objects.update_or_create(place_id=data['place_id'], defaults=defaults)
        return address, created

    def __str__(self):
        return self.formatted or self.place_id or "Unresolved address"
