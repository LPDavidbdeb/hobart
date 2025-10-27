import sys
import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView
from django.contrib import messages
from django.db.models import Q
from .models import Address, AddressValidationLog, AddressStatus
from .utils import run_address_validation_batch
from employees.models import EmployeeProfile
from client.models import Client
from DAO.adresses_DAO import GoogleMapsClient

# --- Permissions ---
def is_admin_or_director(user):
    return user.is_superuser or user.groups.filter(name='Directors').exists()

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
def search_address_api(request):
    try:
        query = request.GET.get('query', '')
        client_pk = request.GET.get('client_pk')

        if not query:
            return JsonResponse({'error': 'A query parameter is required.'}, status=400)

        suggestions = []
        gmaps_client = GoogleMapsClient()

        local_results = Address.objects.filter(
            Q(formatted__icontains=query) |
            Q(street_number__icontains=query) |
            Q(route__icontains=query) |
            Q(locality__icontains=query) |
            Q(postal_code__icontains=query)
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
