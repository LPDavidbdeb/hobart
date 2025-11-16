# routing/services.py
from DAO.adresses_DAO import GoogleMapsClient
from .models import Route
from address.models import Address, PostalCode

def get_or_create_route(technician_postal_code: PostalCode, customer_address: Address):
    """
    Gets a route from the cache or creates it by calling the Google Maps API via the DAO.
    """

    # 1. Try to get from cache first
    try:
        return Route.objects.get(
            origin_postal_code=technician_postal_code.code,
            destination_address_id=customer_address.id
        )
    except Route.DoesNotExist:
        # 2. If not in cache, call the API via the DAO
        if not technician_postal_code.location or not customer_address.location:
            # Cannot calculate a route without valid coordinates
            return None

        try:
            gmaps = GoogleMapsClient()
            directions_result = gmaps.get_directions(
                origin_lat=technician_postal_code.location.y,
                origin_lng=technician_postal_code.location.x,
                dest_lat=customer_address.location.y,
                dest_lng=customer_address.location.x
            )
            
            if not directions_result:
                raise ValueError("No route found by Google Maps API")

            # 3. Parse the response and create the cache entry
            route = Route.objects.create(
                origin_postal_code=technician_postal_code.code,
                destination_address_id=customer_address.id,
                distance_metres=directions_result['distance_metres'],
                duration_seconds=directions_result['duration_seconds'],
                raw_response=directions_result['raw_response']
            )
            return route

        except ValueError as e: # Catches API key errors from the DAO
            print(f"Configuration error: {e}")
            return None
        except Exception as e:
            # Handle other potential errors (API errors, network issues, etc.)
            print(f"Error fetching directions: {e}")
            return None
