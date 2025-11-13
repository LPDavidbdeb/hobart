import sys
import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, View
from django.contrib import messages
from django.db.models import Q
from shapely.constructive import centroid

from .models import Address, AddressValidationLog, AddressStatus, FSA
from organization.models import NestedTerritory # Import NestedTerritory
from .utils import run_address_validation_batch
from employees.models import EmployeeProfile
from client.models import Client
from DAO.adresses_DAO import GoogleMapsClient

# --- Permissions ---
def is_admin_or_director(user):
    return user.is_superuser or user.groups.filter(name='Directors').exists()

# --- FSA Search View ---
class FSASearchView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = 'address/fsa_search.html'

    def test_func(self):
        # For Phase 1, only superusers can access this page
        return self.request.user.is_superuser

    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        territories = []
        if query:
            # Search NestedTerritory excluding FSA, POSTAL_CODE, and ADDRESS types
            territories = NestedTerritory.objects.filter(
                Q(name__icontains=query)
            ).exclude(
                type__in=[
                    NestedTerritory.TerritoryType.FSA,
                    NestedTerritory.TerritoryType.POSTAL_CODE,
                    NestedTerritory.TerritoryType.ADDRESS
                ]
            ).order_by('name')[:20] # Limit results for display

        return render(request, self.template_name, {'territories': territories, 'query': query})

# --- Dashboard View ---
class AddressHealthDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = AddressValidationLog
    template_name = 'address/health_dashboard.html'
    context_object_name = 'logs'
    ordering = ['-timestamp']

    def test_func(self):
        return is_admin_or_director(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logs_data = list(self.get_queryset().values(
            'timestamp', 'clients_complete', 'clients_incomplete', 'clients_missing',
            'employees_complete', 'employees_incomplete', 'employees_missing'
        ).order_by('timestamp'))
        context['logs_json'] = json.dumps(logs_data, default=str)
        return context

    def post(self, request, *args, **kwargs):
        try:
            results = run_address_validation_batch()
            AddressValidationLog.objects.create(run_by=request.user, **results)
            messages.success(request, "Successfully ran address validation and created a new log entry.")
        except Exception as e:
            messages.error(request, f"An error occurred during the validation run: {e}")
        return redirect('address:health_dashboard')

# --- API Views ---
@login_required
def fsa_autocomplete_api(request):
    if not request.user.is_superuser: # For Phase 1, only superusers
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    query = request.GET.get('term', '')
    if len(query) < 2: # Don't search for less than 2 characters
        return JsonResponse([], safe=False)

    # Search NestedTerritory excluding FSA, POSTAL_CODE, and ADDRESS types
    territories = NestedTerritory.objects.filter(
        Q(name__icontains=query)
    ).exclude(
        type__in=[
            NestedTerritory.TerritoryType.FSA,
            NestedTerritory.TerritoryType.POSTAL_CODE,
            NestedTerritory.TerritoryType.ADDRESS
        ]
    ).order_by('name')

    results = [
        {
            'id': territory.id,
            'label': f"{territory.name} ({territory.get_type_display()}) - Clients: {territory.client_count}",
            'value': territory.name # The value to put in the search box
        }
        for territory in territories
    ]
    return JsonResponse(results, safe=False)

@login_required
def get_territory_fsas_api(request, territory_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Permission denied.'}, status=403)

    try:
        territory = get_object_or_404(NestedTerritory, pk=territory_id)
        # Get all descendants that are of type FSA
        fsa_territories = territory.get_descendants().filter(type=NestedTerritory.TerritoryType.FSA)
        
        fsas_data = [
            {
                'name': fsa.name,
                'client_count': fsa.client_count
            }
            for fsa in fsa_territories
        ]
        return JsonResponse(fsas_data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def search_address_api(request):
    try:
        query = request.GET.get('query', '')
        client_pk = request.GET.get('client_pk')

        if not query:
            return JsonResponse({'error': 'A query parameter is required.'}, status=400)

        suggestions = []
        gmaps_client = GoogleMapsClient()

        # CORRECTED: Only query on the 'formatted' field as others are now properties
        local_results = Address.objects.filter(
            Q(formatted__icontains=query)
        )[:5]

        suggestions.extend([
            {'formatted_address': addr.formatted, 'place_id': addr.place_id, 'source': 'database'}
            for addr in local_results
        ])

        if client_pk and len(suggestions) < 5:
            try:
                client_instance = Client.objects.select_related('client_group').get(pk=client_pk)
                business_name = client_instance.client_group.name if client_instance.client_group else client_instance.name
                
                if business_name:
                    place_search_results = gmaps_client.place_search(business_name, query)
                    existing_place_ids = {s['place_id'] for s in suggestions}
                    for result in place_search_results:
                        place_id = result.get('place_id')
                        if place_id not in existing_place_ids:
                            suggestions.append({
                                'formatted_address': result.get('formatted_address'),
                                'place_id': place_id,
                                'source': 'google_place'
                            })
            except Client.DoesNotExist:
                pass

        if len(suggestions) < 5:
            api_results = gmaps_client.geocode(query)
            existing_place_ids = {s['place_id'] for s in suggestions}
            for result in api_results:
                place_id = result.get('place_id')
                if place_id not in existing_place_ids:
                    suggestions.append({
                        'formatted_address': result.get('formatted_address'),
                        'place_id': place_id,
                        'source': 'google_geocode'
                    })
        
        return JsonResponse({'suggestions': suggestions[:5]})

    except Exception as e:
        print(f"--- ERROR IN search_address_api: {e} ---", file=sys.stderr)
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def set_employee_address_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    try:
        data = json.loads(request.body)
        employee_pk = data.get('employee_pk')
        place_id = data.get('place_id')

        if not employee_pk or not place_id:
            return JsonResponse({'error': 'employee_pk and place_id are required.'}, status=400)

        employee_profile = get_object_or_404(EmployeeProfile, pk=employee_pk)
        gmaps_client = GoogleMapsClient()
        results = gmaps_client.geocode_by_place_id(place_id)
        
        if not results:
            return JsonResponse({'error': 'Could not retrieve details for the selected address.'}, status=500)
        
        address_obj, created = Address.save_from_google_maps_data(results[0])

        if not address_obj:
            return JsonResponse({'error': 'Failed to save address data.'}, status=500)

        reasons = []
        if address_obj.is_degenerate():
            status_obj = AddressStatus.objects.get(name='INCOMPLETE')
            reasons = address_obj.get_degeneracy_reasons()
        else:
            status_obj = AddressStatus.objects.get(name='COMPLETE')

        employee_profile.address = address_obj
        employee_profile.address_status = status_obj
        employee_profile.save(update_fields=['address', 'address_status'])

        response_data = {
            'success': True,
            'formatted_address': address_obj.formatted,
            'status': {
                'name': status_obj.name,
                'badge_class': status_obj.badge_class,
                'reasons': reasons
            }
        }
        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def set_client_address_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required.'}, status=405)

    try:
        data = json.loads(request.body)
        client_pk = data.get('client_pk')
        place_id = data.get('place_id')

        if not client_pk or not place_id:
            return JsonResponse({'error': 'client_pk and place_id are required.'}, status=400)

        client_instance = get_object_or_404(Client, pk=client_pk)
        gmaps_client = GoogleMapsClient()
        results = gmaps_client.geocode_by_place_id(place_id)
        
        if not results:
            return JsonResponse({'error': 'Could not retrieve details for the selected address.'}, status=500)
        
        address_obj, created = Address.save_from_google_maps_data(results[0])

        if not address_obj:
            return JsonResponse({'error': 'Failed to save address data.'}, status=500)

        reasons = []
        if address_obj.is_degenerate():
            status_obj = AddressStatus.objects.get(name='INCOMPLETE')
            reasons = address_obj.get_degeneracy_reasons()
        else:
            status_obj = AddressStatus.objects.get(name='COMPLETE')

        client_instance.address = address_obj
        client_instance.address_status = status_obj
        client_instance.save(update_fields=['address', 'address_status'])

        response_data = {
            'success': True,
            'formatted_address': address_obj.formatted,
            'status': {
                'name': status_obj.name,
                'badge_class': status_obj.badge_class,
                'reasons': reasons
            }
        }
        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


from django.shortcuts import render
import json

# views.py
from django.shortcuts import render
from django.db.models import Q, Sum
from decimal import Decimal
from math import log2
from address.models import Address, FSA
from client.models import Client


import json
from django.shortcuts import render
from django.db.models import Sum, Value
from django.contrib.gis.db.models.functions import GeoFunc
from math import log2
from client.models import Client
from address.models import FSA
from django.contrib.gis.db import models as gis_models

# --- Define Custom PostGIS Function ---
class SimplifyPreserveTopology(GeoFunc):
    function = 'ST_SimplifyPreserveTopology'
    # This line tells Django the function returns a MultiPolygonField
    output_field = gis_models.MultiPolygonField()

def fsa_region_map(request, region_prefix):
    prefix = region_prefix.upper()

    # FIX 1: Use the legacy 'postal_code' field on the Client model.
    # The ORM can filter on this because it's a real database column.
    clients = Client.objects.filter(
        postal_code__istartswith=prefix,
        address__latitude__isnull=False,
        address__longitude__isnull=False
    ).select_related('address')

    if not clients.exists():
        # Fallback centroid and zoom (Roughly Canada)
        centroid = [56, -96]
        zoom = 4
    else:
        # Compute spherical centroid (mean of lat/lng)
        count = clients.count()
        total_lat = sum([float(c.address.latitude) for c in clients])
        total_lng = sum([float(c.address.longitude) for c in clients])
        centroid = [total_lat / count, total_lng / count]

        # Compute zoom based on total land_area of FSAs starting with prefix
        total_land_area = FSA.objects.filter(
            code__istartswith=prefix
        ).aggregate(total=Sum('land_area'))['total'] or 1000

        # Approximate zoom heuristic
        zoom = max(2, min(12, int(8 - log2(total_land_area / 100))))

        # 2. OPTIMIZED GEOJSON GENERATION (Database-Side)
        # 0.005 tolerance is roughly ~500m.
        TOLERANCE = 0.005

        # Fetch only what we need. The DB does the heavy lifting.
        fsa_data = FSA.objects.filter(
            code__istartswith=prefix,
            boundary__isnull=False
        ).annotate(
            simple_geom=SimplifyPreserveTopology('boundary', Value(TOLERANCE))
        ).values('code', 'client_count', 'simple_geom')

        fsa_features = []
        for entry in fsa_data:
            if entry['simple_geom']:
                # PostGIS usually returns the geometry as a GEOSGeometry object here.
                # We use .json to get its GeoJSON string representation, then parse it.
                geom = entry['simple_geom']
                geom_dict = json.loads(geom.json) if hasattr(geom, 'json') else json.loads(geom)

                fsa_features.append({
                    "type": "Feature",
                    "properties": {
                        "code": entry['code'],
                        "client_count": entry['client_count']
                    },
                    "geometry": geom_dict
                })
        fsa_geojson = json.dumps({
            "type": "FeatureCollection",
            "features": fsa_features
        })


    zoom = 11
    # fsa_geojson = """
    # {
    #   "type": "FeatureCollection",
    #   "features": [
    #     {
    #       "type": "Feature",
    #       "properties": {"code": "H2X"},
    #       "geometry": {
    #         "type": "Polygon",
    #         "coordinates": [[
    #           [-73.58, 45.50],
    #           [-73.55, 45.50],
    #           [-73.55, 45.52],
    #           [-73.58, 45.52],
    #           [-73.58, 45.50]
    #         ]]
    #       }
    #     }
    #   ]
    # }
    # """
    context = {
        "centroid": centroid,  # [lat, lng]
        "zoom": zoom,
        "fsa_geojson": fsa_geojson,  # Add to context
    }

    return render(request, "address/fsa_region_map.html", context)
