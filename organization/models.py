from django.db import models
from address.models import FSA

class CodeDimension(models.Model):
    """An abstract base class for simple code/description dimension models."""
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="The unique code for this item.")
    description = models.CharField(max_length=255, blank=True, help_text="The description for this code.")

    class Meta:
        abstract = True
        ordering = ['description', 'code']

    def __str__(self):
        return f"{self.description} ({self.code})" if self.description else self.code

class Territory(models.Model):
    """Represents a standardized geographical area, such as a Province, Region, or City."""
    class TerritoryType(models.TextChoices):
        PROVINCE = 'PROVINCE', 'Province'
        REGION = 'REGION', 'Regional Municipality' # RCM in Quebec
        CITY = 'CITY', 'City'

    name = models.CharField(max_length=100, db_index=True)
    type = models.CharField(max_length=20, choices=TerritoryType.choices, db_index=True)
    fsas = models.ManyToManyField(FSA, blank=True, related_name='territories', help_text="The FSAs that define this territory.")
    boundary_geojson = models.JSONField(null=True, blank=True, help_text="GeoJSON representation of the territory's boundary.")

    class Meta:
        unique_together = ('name', 'type') # Ensures you don't have two "Quebec" provinces
        verbose_name_plural = "Territories"
        ordering = ['type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

class TravelCostParameters(models.Model):
    """Stores a historical record of configurable parameters for calculating travel costs."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    name = models.CharField(max_length=100, default="Default Travel Costs")
    cost_per_minute = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    cost_per_km = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    truck_depreciation_fixed_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    supply_charge_fixed_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)

    class Meta:
        verbose_name_plural = "Travel Cost Parameters"
        ordering = ['-created_at']  # Order by most recent first

    def __str__(self):
        return f"{self.name} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
