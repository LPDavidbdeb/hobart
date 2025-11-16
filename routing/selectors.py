from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from employees.models import EmployeeProfile
from address.models import Address

def find_nearby_technicians(customer_address: Address, radius_km: int = 600, limit: int = 20):
    """
    Finds technicians close to a customer address in two stages.

    1.  Filters technicians within a broad radius using an efficient PostGIS query.
    2.  Annotates the results with the precise distance and returns the closest ones.
    """
    customer_location = customer_address.location
    if not customer_location:
        return EmployeeProfile.objects.none()

    # 1. Broad filter using distance_lte, which works correctly with geographic coordinates.
    # This is the corrected line.
    nearby_techs_qs = EmployeeProfile.objects.filter(
        user__is_active=True,
        role=EmployeeProfile.Role.TECHNICIAN,
        postal_code__location__distance_lte=(customer_location, D(km=radius_km))
    ).select_related('user', 'postal_code') # Added select_related for efficiency

    # 2. Annotate with exact distance, order by it, and take the closest 'limit'
    closest_techs_qs = nearby_techs_qs.annotate(
        distance=Distance('postal_code__location', customer_location)
    ).order_by('distance')[:limit]

    return closest_techs_qs
