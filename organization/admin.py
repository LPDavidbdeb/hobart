from django.contrib import admin
from .models import Territory, TravelCostParameters

@admin.register(Territory)
class TerritoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'get_fsa_count')
    list_filter = ('type',)
    search_fields = ('name',)
    filter_horizontal = ('fsas',) # For ManyToMany field

    def get_fsa_count(self, obj):
        return obj.fsas.count()
    get_fsa_count.short_description = '# of FSAs'

@admin.register(TravelCostParameters)
class TravelCostParametersAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'cost_per_minute', 'cost_per_km', 'truck_depreciation_fixed_cost', 'supply_charge_fixed_cost')
    list_filter = ('created_at',)
    search_fields = ('name',)
    readonly_fields = ('created_at',) # Ensure timestamp is not manually editable
