import json
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_POST

from client.models import Client
from employees.models import EmployeeProfile
from .selectors import find_nearby_technicians
from .services import get_or_create_route

@login_required
def find_best_technician_view(request, client_id):
    """
    Finds and ranks the best technicians for a given client based on travel distance and time.
    """
    client = get_object_or_404(Client.objects.select_related('address'), pk=client_id)

    if not client.address or not client.address.location:
        # We can't search without a valid, geocoded address for the client.
        # Consider adding a message for the user.
        return HttpResponseBadRequest("Client address is not geocoded.")

    # 1. Get a shortlist of nearby technicians using the efficient PostGIS query.
    nearby_technicians = find_nearby_technicians(customer_address=client.address, limit=20)

    # 2. For each technician in the shortlist, get the detailed route from the cache or API.
    technician_route_data = []
    for tech in nearby_technicians:
        if not tech.postal_code:
            continue # Skip technicians without a postal code.

        route = get_or_create_route(
            technician_postal_code=tech.postal_code,
            customer_address=client.address
        )

        if route:
            technician_route_data.append({
                'technician': tech,
                'distance_km': route.distance_metres / 1000,
                'duration_minutes': route.duration_seconds / 60,
            })

    # 3. Sort the final list by duration.
    technician_route_data.sort(key=lambda x: x['duration_minutes'])

    context = {
        'client': client,
        'technicians_with_routes': technician_route_data,
    }

    return render(request, 'routing/technician_results.html', context)


@login_required
@require_POST
def calculate_route_api(request):
    """
    API endpoint to calculate and return a single route between a client and a technician.
    Now includes the encoded polyline for drawing the route on the map.
    """
    try:
        data = json.loads(request.body)
        client_id = data.get('client_id')
        technician_id = data.get('technician_id')

        if not client_id or not technician_id:
            return JsonResponse({'success': False, 'error': 'Client and Technician IDs are required.'}, status=400)

        client = get_object_or_404(Client.objects.select_related('address'), pk=client_id)
        technician = get_object_or_404(EmployeeProfile.objects.select_related('postal_code'), pk=technician_id)

        if not client.address or not client.address.location:
            return JsonResponse({'success': False, 'error': 'Client address is not geocoded.'}, status=400)
        if not technician.postal_code or not technician.postal_code.location:
            return JsonResponse({'success': False, 'error': 'Technician postal code is not geocoded.'}, status=400)

        route = get_or_create_route(
            technician_postal_code=technician.postal_code,
            customer_address=client.address
        )

        if route and route.raw_response and 'routes' in route.raw_response and route.raw_response['routes']:
            encoded_polyline = route.raw_response['routes'][0].get('polyline', {}).get('encodedPolyline')
            return JsonResponse({
                'success': True,
                'distance_km': route.distance_metres / 1000,
                'duration_minutes': route.duration_seconds / 60,
                'polyline': encoded_polyline,
            })
        elif route:
            # Route was found in cache but might not have polyline data
            return JsonResponse({
                'success': True,
                'distance_km': route.distance_metres / 1000,
                'duration_minutes': route.duration_seconds / 60,
                'polyline': None, # Explicitly return null if not available
            })
        else:
            return JsonResponse({'success': False, 'error': 'Could not calculate route.'}, status=500)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
