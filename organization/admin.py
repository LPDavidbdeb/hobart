from django.contrib import admin
from mptt.admin import DraggableMPTTAdmin
from .models import NestedTerritory, Territory, TravelCostParameters

@admin.register(NestedTerritory)
class NestedTerritoryAdmin(DraggableMPTTAdmin):
    """Admin interface for the hierarchical NestedTerritory model."""
    # Display the pre-calculated client_count field directly
    list_display = ('tree_actions', 'indented_title', 'type', 'client_count')
    list_display_links = ('indented_title',)
    search_fields = ('name',)
    list_filter = ('type',)

# The old Territory model is not registered in the admin anymore
# @admin.register(Territory)
# class TerritoryAdmin(admin.ModelAdmin):
#     ...

@admin.register(TravelCostParameters)
class TravelCostParametersAdmin(admin.ModelAdmin):
    """Admin interface for TravelCostParameters."""
    list_display = ('name', 'created_at', 'cost_per_minute', 'cost_per_km')
    list_filter = ('created_at',)
    search_fields = ('name',)
