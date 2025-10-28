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
    # --- Core Fields ---
    formatted = models.CharField(max_length=255, blank=True, null=True)
    place_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    raw_response = models.JSONField(null=True, blank=True)

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
        """Checks if the address is missing critical components using the intelligent properties."""
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

        defaults = {
            'formatted': data.get('formatted_address'),
            'latitude': decimal.Decimal(data['geometry']['location']['lat']),
            'longitude': decimal.Decimal(data['geometry']['location']['lng']),
            'raw_response': data, # Store the entire response
        }

        address, created = cls.objects.update_or_create(place_id=data['place_id'], defaults=defaults)
        return address, created

    def __str__(self):
        return self.formatted or self.place_id or "Unresolved address"
