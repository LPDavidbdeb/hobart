from django.db import models

# Create your models here.
# routing/models.py
from django.contrib.gis.db import models as gis_models
from django.db import models


class Route(models.Model):
    """
    Stores the calculated travel distance and time between two points.
    This acts as a cache to minimize expensive API calls.

    The origin is a PostalCode (technician's base) and the destination
    is an Address (customer's location).
    """
    # Using CharFields to store identifiers for origin/destination
    # This is more flexible than direct ForeignKeys if locations are not always model instances
    origin_postal_code = models.CharField(max_length=10, db_index=True)
    destination_address_id = models.PositiveIntegerField(db_index=True)

    # Data from the Directions API
    distance_metres = models.PositiveIntegerField()
    duration_seconds = models.PositiveIntegerField()

    # Store the raw response for future use or debugging
    raw_response = models.JSONField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ensure we only store one route from an origin to a destination
        unique_together = ('origin_postal_code', 'destination_address_id')
        verbose_name = "Cached Route"
        verbose_name_plural = "Cached Routes"

    def __str__(self):
        return f"Route from {self.origin_postal_code} to Address {self.destination_address_id}"
