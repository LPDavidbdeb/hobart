import requests
import re
from django.conf import settings
from address.models import Address

class GoogleMapsClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or getattr(settings, "GOOGLE_MAPS_API_KEY", None)
        if not self.api_key:
            raise ValueError("Google Maps API key is required.")
        self.base_url = "https://maps.googleapis.com/maps/api"
        self.session = requests.Session()

    def geocode(self, address: str):
        """
        Geocodes a human-readable address string. Biased towards Canada.
        """
        endpoint = f"{self.base_url}/geocode/json"
        params = {"address": address, "key": self.api_key, "components": "country:CA"}
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            print(f"Error during geocoding request: {e}")
            return []

    def geocode_by_place_id(self, place_id: str):
        """
        Geocodes a specific Place ID to get its full details.
        """
        endpoint = f"{self.base_url}/geocode/json"
        params = {"place_id": place_id, "key": self.api_key}
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            print(f"Error during place_id geocoding request: {e}")
            return []

    def place_search(self, business_name: str, address_query: str):
        """
        Searches for a business by name and address using the Place Search API.
        """
        endpoint = f"{self.base_url}/place/textsearch/json"
        full_query = f"{business_name} {address_query}"
        params = {
            "query": full_query,
            "key": self.api_key,
            "region": "ca"
        }
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            print(f"Error during place search request: {e}")
            return []

    def geocode_and_save(self, address_string: str):
        results = self.geocode(address_string)
        if results:
            best_result = results[0]
            address_obj, created = Address.save_from_google_maps_data(best_result)
            return address_obj
        return None

    def geocode_postal_code(self, postal_code: str):
        """
        Geocodes a Canadian postal code.
        """
        endpoint = f"{self.base_url}/geocode/json"
        params = {
            "address": postal_code,
            "key": self.api_key,
            "components": "country:CA|postal_code:" + postal_code,
        }
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            print(f"Error during postal code geocoding request: {e}")
            return []

    def get_directions(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float):
        """
        Gets driving directions and travel metrics between two points using the Routes API.
        Returns a dictionary with distance_metres, duration_seconds, and the raw response.
        """
        endpoint = "https://routes.googleapis.com/directions/v2:computeRoutes"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
        }
        payload = {
            "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
            "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
        }
        try:
            response = self.session.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            if not data or "routes" not in data or not data["routes"]:
                return None

            route = data["routes"][0]
            # Duration is a string like "123s", so we parse the integer value.
            duration_str = route.get("duration", "0s")
            duration_seconds = int(re.search(r'\d+', duration_str).group())

            return {
                "distance_metres": route.get("distanceMeters", 0),
                "duration_seconds": duration_seconds,
                "raw_response": data,
            }
        except requests.exceptions.RequestException as e:
            print(f"Error during directions request: {e}")
            return None

    def get_distance_matrix(self, origin_place_ids: list, destination_place_ids: list, mode='driving'):
        endpoint = f"{self.base_url}/distancematrix/json"
        params = {
            "origins": "|".join([f"place_id:{pid}" for pid in origin_place_ids]),
            "destinations": "|".join([f"place_id:{pid}" for pid in destination_place_ids]),
            "mode": mode,
            "key": self.api_key,
        }
        try:
            response = self.session.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error during distance matrix request: {e}")
            return None

    def compute_routes_matrix(self, origin_place_ids: list, destination_place_ids: list, routing_preference='TRAFFIC_AWARE'):
        endpoint = "https://routes.googleapis.com/distanceMatrix/v2"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters,status",
        }
        payload = {
            "origins": [{"waypoint": {"place_id": pid}} for pid in origin_place_ids],
            "destinations": [{"waypoint": {"place_id": pid}} for pid in destination_place_ids],
            "travelMode": "DRIVE",
            "routingPreference": routing_preference,
        }
        try:
            response = self.session.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error during compute routes matrix request: {e}")
            return None
