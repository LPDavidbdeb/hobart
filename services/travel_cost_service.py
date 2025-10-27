from DAO.adresses_DAO import GoogleMapsClient
from organization.models import TravelCostParameters
from address.models import Address

def calculate_driving_cost(origin_address: Address, destination_address: Address):
    """
    Calculates the total travel cost between two addresses using the most recent cost parameters.

    Args:
        origin_address: The starting Address object.
        destination_address: The destination Address object.

    Returns:
        A dictionary containing the detailed cost breakdown and total, or None if calculation fails.
    """
    if not origin_address or not destination_address or not origin_address.place_id or not destination_address.place_id:
        return None

    # 1. Get distance and duration from Google Maps
    gmaps_client = GoogleMapsClient()
    distance_matrix = gmaps_client.get_distance_matrix(
        origin_place_id=origin_address.place_id,
        destination_place_id=destination_address.place_id
    )

    if not distance_matrix:
        return None

    # 2. Get the most recent cost parameters from the database
    try:
        # Use .latest() to be explicit about getting the most recent record.
        params = TravelCostParameters.objects.latest('created_at')
    except TravelCostParameters.DoesNotExist:
        return {"error": "Travel cost parameters not configured."}

    # 3. Perform the calculation
    distance_km = distance_matrix['distance_meters'] / 1000
    duration_minutes = distance_matrix['duration_seconds'] / 60

    time_cost = duration_minutes * float(params.cost_per_minute)
    gas_cost = distance_km * float(params.cost_per_km)
    total_cost = time_cost + gas_cost + float(params.truck_depreciation_fixed_cost) + float(params.supply_charge_fixed_cost)

    return {
        "total_cost": round(total_cost, 2),
        "time_cost": round(time_cost, 2),
        "gas_cost": round(gas_cost, 2),
        "truck_depreciation": float(params.truck_depreciation_fixed_cost),
        "supply_charge": float(params.supply_charge_fixed_cost),
        "distance_km": round(distance_km, 2),
        "duration_minutes": round(duration_minutes, 2),
    }
