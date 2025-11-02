from django.contrib.gis.db import models as gis_models
from mptt.models import MPTTModel, TreeForeignKey
# from address.models import FSA # This direct import causes a circular dependency

# --- New Hierarchical Model ---
class NestedTerritory(MPTTModel):
    """ 
    Represents a full hierarchical geographical structure from Country down to a specific Address.
    Managed by django-mptt.
    """
    class TerritoryType(gis_models.TextChoices):
        COUNTRY = 'COUNTRY', 'Country'
        PROVINCE = 'PROVINCE', 'Province'
        REGION = 'REGION', 'Regional Municipality'
        CITY = 'CITY', 'City'
        FSA = 'FSA', 'Forward Sortation Area'
        POSTAL_CODE = 'POSTAL_CODE', 'Postal Code'
        ADDRESS = 'ADDRESS', 'Specific Address'

    class BoundaryStatus(gis_models.TextChoices):
        UNPROCESSED = 'UNPROCESSED', 'Unprocessed'
        MATCHED = 'MATCHED', 'Matched'
        NO_SHAPEFILE_MATCH = 'NO_SHAPEFILE_MATCH', 'No Shapefile Match'
        NEEDS_WIKI_SCRAPE = 'NEEDS_WIKI_SCRAPE', 'Needs Wiki Scrape'
        WIKI_SCRAPED = 'WIKI_SCRAPED', 'Wiki Scraped'
        MANUAL_REVIEW_NEEDED = 'MANUAL_REVIEW', 'Manual Review Needed'

    name = gis_models.CharField(max_length=255, db_index=True, help_text="The name of the territory (e.g., 'Canada', 'Quebec', 'Montreal', 'H2X', 'H2X 1X6').")
    type = gis_models.CharField(max_length=20, choices=TerritoryType.choices, db_index=True)
    code = gis_models.CharField(max_length=50, null=True, blank=True, db_index=True, help_text="An official code for the territory, like a CDUID or PRUID.")
    parent = TreeForeignKey('self', on_delete=gis_models.CASCADE, null=True, blank=True, related_name='children')
    tree_name = gis_models.CharField(max_length=100, db_index=True, default='Default', help_text="The name of the hierarchy this node belongs to (e.g., 'Electoral', 'Administrative').")

    client_count = gis_models.PositiveIntegerField(default=0, editable=False, help_text="Total number of clients in this territory and all its descendants.")
    boundary = gis_models.MultiPolygonField(srid=4326, null=True, blank=True, help_text="The geographical boundary of the territory.")
    scraped_data = gis_models.JSONField(null=True, blank=True, help_text="Raw data scraped from external sources like Wikipedia.")
    boundary_status = gis_models.CharField(max_length=20, choices=BoundaryStatus.choices, default=BoundaryStatus.UNPROCESSED, db_index=True)

    lft = gis_models.PositiveIntegerField(editable=False, null=True)
    rght = gis_models.PositiveIntegerField(editable=False, null=True)
    level = gis_models.PositiveIntegerField(editable=False, null=True)
    tree_id = gis_models.PositiveIntegerField(editable=False, null=True)

    class MPTTMeta:
        order_insertion_by = ['name']

    class Meta:
        unique_together = ('tree_name', 'parent', 'name', 'type')
        verbose_name = "Nested Territory"
        verbose_name_plural = "Nested Territories"

    def __str__(self):
        return f"{self.name} ({self.tree_name})"

# --- Existing Models (Untouched) ---
class CodeDimension(gis_models.Model):
    """An abstract base class for simple code/description dimension models."""
    code = gis_models.CharField(max_length=50, unique=True, db_index=True, help_text="The unique code for this item.")
    description = gis_models.CharField(max_length=255, blank=True, help_text="The description for this code.")

    class Meta:
        abstract = True
        ordering = ['description', 'code']

    def __str__(self):
        return f"{self.description} ({self.code})" if self.description else self.code

class Territory(gis_models.Model):
    """Represents a standardized geographical area, such as a Province, Region, or City."""
    class TerritoryType(gis_models.TextChoices):
        PROVINCE = 'PROVINCE', 'Province'
        REGION = 'REGION', 'Regional Municipality' # RCM in Quebec
        CITY = 'CITY', 'City'

    name = gis_models.CharField(max_length=100, db_index=True)
    type = gis_models.CharField(max_length=20, choices=TerritoryType.choices, db_index=True)
    fsas = gis_models.ManyToManyField('address.FSA', blank=True, related_name='territories', help_text="The FSAs that define this territory.")
    boundary_geojson = gis_models.JSONField(null=True, blank=True, help_text="GeoJSON representation of the territory's boundary.")

    class Meta:
        unique_together = ('name', 'type') # Ensures you don't have two "Quebec" provinces
        verbose_name_plural = "Territories"
        ordering = ['type', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

class TravelCostParameters(gis_models.Model):
    """Stores a historical record of configurable parameters for calculating travel costs."""
    created_at = gis_models.DateTimeField(auto_now_add=True, db_index=True)
    name = gis_models.CharField(max_length=100, default="Default Travel Costs")
    cost_per_minute = gis_models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    cost_per_km = gis_models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    truck_depreciation_fixed_cost = gis_models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    supply_charge_fixed_cost = gis_models.DecimalField(max_digits=10, decimal_places=2, default=0.0)

    class Meta:
        verbose_name_plural = "Travel Cost Parameters"
        ordering = ['-created_at']  # Order by most recent first

    def __str__(self):
        return f"{self.name} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
