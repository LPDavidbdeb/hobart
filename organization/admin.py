from django.contrib import admin
from .models import Territory, TravelCostParameters
from address.models import FSA # FSA is now in the address app

@admin.register(FSA)
class FSAAdmin(admin.ModelAdmin):
    list_display = ('code', 'description')
    search_fields = ('code', 'description')

@admin.register(Territory)
class TerritoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'description', 'get_fsas')
    search_fields = ('code', 'description')
    filter_horizontal = ('fsas',) # For ManyToMany field

    def get_fsas(self, obj):
        return ", ".join([fsa.code for fsa in obj.fsas.all()])
    get_fsas.short_description = 'FSAs'

@admin.register(TravelCostParameters)
class TravelCostParametersAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'cost_per_minute', 'cost_per_km', 'truck_depreciation_fixed_cost', 'supply_charge_fixed_cost')
    list_filter = ('created_at',)
    search_fields = ('name',)
    readonly_fields = ('created_at',) # Ensure timestamp is not manually editable
