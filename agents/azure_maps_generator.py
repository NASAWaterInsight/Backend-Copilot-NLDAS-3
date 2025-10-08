import requests
import json
from typing import Dict, List, Any, Optional, Tuple

class AzureMapsGenerator:
    """Generator for creating Azure Maps configurations and handling map operations."""
    
    def __init__(self, subscription_key: str):
        self.subscription_key = subscription_key
        self.base_url = "https://atlas.microsoft.com"
        
    def create_map(self, coordinates: List[Tuple[float, float]], 
                   data_points: List[Dict[str, Any]], 
                   style: str = "satellite") -> Dict[str, Any]:
        """Create a map configuration with given coordinates and data points."""
        
        # Calculate center point from coordinates
        center = self._calculate_center(coordinates) if coordinates else [0, 0]
        
        # Create map configuration
        map_config = {
            "subscription_key": self.subscription_key,
            "center": center,
            "zoom": 10,
            "style": style,
            "data_sources": [],
            "layers": []
        }
        
        # Add data points as markers
        if data_points:
            markers_data = self._create_markers_data(data_points)
            map_config["data_sources"].append(markers_data)
            map_config["layers"].append({
                "type": "symbol",
                "source": "markers",
                "options": {
                    "iconOptions": {
                        "image": "pin-blue",
                        "allowOverlap": True
                    }
                }
            })
        
        # Add coordinate path if multiple coordinates
        if len(coordinates) > 1:
            path_data = self._create_path_data(coordinates)
            map_config["data_sources"].append(path_data)
            map_config["layers"].append({
                "type": "line",
                "source": "path",
                "options": {
                    "strokeColor": "#2563eb",
                    "strokeWidth": 3
                }
            })
        
        return map_config
    
    def search_location(self, query: str, location: Optional[Tuple[float, float]] = None) -> Dict[str, Any]:
        """Search for a location using Azure Maps Search API."""
        url = f"{self.base_url}/search/fuzzy/json"
        params = {
            "subscription-key": self.subscription_key,
            "api-version": "1.0",
            "query": query,
            "limit": 5
        }
        
        if location:
            params["lat"] = location[1]
            params["lon"] = location[0]
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": f"Search failed: {str(e)}"}
    
    def calculate_route(self, start: Tuple[float, float], 
                       end: Tuple[float, float], 
                       waypoints: List[Tuple[float, float]] = None) -> Dict[str, Any]:
        """Calculate route between points using Azure Maps Route API."""
        url = f"{self.base_url}/route/directions/json"
        
        # Build route points
        route_points = [f"{start[1]},{start[0]}"]
        if waypoints:
            route_points.extend([f"{wp[1]},{wp[0]}" for wp in waypoints])
        route_points.append(f"{end[1]},{end[0]}")
        
        params = {
            "subscription-key": self.subscription_key,
            "api-version": "1.0",
            "query": ":".join(route_points)
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": f"Route calculation failed: {str(e)}"}
    
    def _calculate_center(self, coordinates: List[Tuple[float, float]]) -> List[float]:
        """Calculate center point from list of coordinates."""
        if not coordinates:
            return [0, 0]
        
        avg_lon = sum(coord[0] for coord in coordinates) / len(coordinates)
        avg_lat = sum(coord[1] for coord in coordinates) / len(coordinates)
        return [avg_lon, avg_lat]
    
    def _create_markers_data(self, data_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create GeoJSON data source for markers."""
        features = []
        for point in data_points:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [point.get("longitude", 0), point.get("latitude", 0)]
                },
                "properties": {
                    "title": point.get("title", ""),
                    "description": point.get("description", ""),
                    "value": point.get("value", "")
                }
            }
            features.append(feature)
        
        return {
            "id": "markers",
            "type": "geojson",
            "data": {
                "type": "FeatureCollection",
                "features": features
            }
        }
    
    def _create_path_data(self, coordinates: List[Tuple[float, float]]) -> Dict[str, Any]:
        """Create GeoJSON data source for path."""
        return {
            "id": "path",
            "type": "geojson",
            "data": {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[coord[0], coord[1]] for coord in coordinates]
                }
            }
        }