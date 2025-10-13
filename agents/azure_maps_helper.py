import os
import logging
from typing import Dict, List, Tuple, Optional

def get_azure_maps_config() -> Dict[str, str]:
    """Get Azure Maps configuration from environment variables"""
    subscription_key = os.environ.get("AZURE_MAPS_SUBSCRIPTION_KEY")
    client_id = os.environ.get("AZURE_MAPS_CLIENT_ID")
    
    if not subscription_key:
        logging.warning("AZURE_MAPS_SUBSCRIPTION_KEY not found in environment")
        return {}
    
    return {
        "subscription_key": subscription_key,
        "client_id": client_id or "",
        "api_version": "1.0"
    }

def create_map_config_for_region(region_bounds: Dict, query: str) -> Dict:
    """
    Create Azure Maps configuration for a specific region
    """
    maps_config = get_azure_maps_config()
    
    if not maps_config:
        # Fallback config without Azure Maps
        return {
            "center": [
                (region_bounds.get("west", -98) + region_bounds.get("east", -98)) / 2,
                (region_bounds.get("south", 39) + region_bounds.get("north", 39)) / 2
            ],
            "zoom": 6,
            "style": "satellite"
        }
    
    # Enhanced config with Azure Maps
    return {
        "center": [
            (region_bounds.get("west", -98) + region_bounds.get("east", -98)) / 2,
            (region_bounds.get("south", 39) + region_bounds.get("north", 39)) / 2
        ],
        "zoom": 6,
        "style": "satellite",
        "subscription_key": maps_config["subscription_key"],
        "client_id": maps_config["client_id"],
        "overlay_mode": True,
        "show_weather_data": True
    }

def enhance_response_with_maps(response_data: Dict, user_query: str) -> Dict:
    """
    Enhance response data with Azure Maps configuration
    """
    maps_config = get_azure_maps_config()
    
    if maps_config and "bounds" in response_data:
        response_data["azure_maps_config"] = create_map_config_for_region(
            response_data["bounds"], 
            user_query
        )
        response_data["maps_available"] = True
    else:
        response_data["maps_available"] = False
    
    return response_data
