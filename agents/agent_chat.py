# agents/agent_chat.py - Merged version with timing, enhanced error handling, and analysis detection
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
from .dynamic_code_generator import execute_custom_code
import numpy as np
import builtins
from .memory_manager import memory_manager

# Load agent info
agent_info_path = os.path.join(os.path.dirname(__file__), "../agent_info.json")
try:
    with open(agent_info_path, "r") as f:
        agent_info = json.load(f)
    
    text_agent_id = agent_info["agents"]["text"]["id"]
    project_endpoint = agent_info["project_endpoint"]
    
    if not text_agent_id:
        raise KeyError("text agent ID is missing or invalid in agent_info.json")
        
except FileNotFoundError:
    raise FileNotFoundError(f"❌ agent_info.json not found at {agent_info_path}. Please run 'create_agents.py'.")
except KeyError as e:
    raise KeyError(f"❌ Missing or invalid key in agent_info.json: {e}")

# Initialize the AI Project Client
project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential()
)

def _get_run(thread_id: str, run_id: str):
    """Handling different versions of the Azure AI SDK"""
    runs_ops = project_client.agents.runs
    if not hasattr(_get_run, "_logged"):
        logging.info(f"agents.runs available methods: {dir(runs_ops)}")
        _get_run._logged = True
    if hasattr(runs_ops, "get"):
        return runs_ops.get(thread_id=thread_id, run_id=run_id)
    if hasattr(runs_ops, "get_run"):
        return runs_ops.get_run(thread_id=thread_id, run_id=run_id)
    if hasattr(runs_ops, "retrieve_run"):
        return runs_ops.retrieve_run(thread_id=thread_id, run_id=run_id)
    raise AttributeError("RunsOperations has no get/get_run/retrieve_run")

def determine_optimal_zoom_level(bounds: dict) -> int:
    """
    Area-based zoom selection with proper exponential scaling
    
    Strategy: Use tiered approach that matches real-world needs
    - Cities (< 1 sq°): 6-15 tiles at zoom 8-9
    - Small states (1-10 sq°): 12-30 tiles at zoom 7-8
    - Medium states (10-100 sq°): 30-80 tiles at zoom 6-7
    - Large states (100-500 sq°): 80-200 tiles at zoom 5-6
    - Huge regions (500-2000 sq°): 150-400 tiles at zoom 4-5
    - Continental (> 2000 sq°): 300-600 tiles at zoom 3-4
    """
    import mercantile
    import math
    
    lat_span = bounds["north"] - bounds["south"]
    lng_span = bounds["east"] - bounds["west"]
    area = lat_span * lng_span
    
    logging.info(f"🗺️ Region bounds: N={bounds['north']:.2f}, S={bounds['south']:.2f}, E={bounds['east']:.2f}, W={bounds['west']:.2f}")
    logging.info(f"📐 Region area: {area:.2f} sq degrees ({lat_span:.2f}° × {lng_span:.2f}°)")
    
    # ✅ NEW: Tiered zoom selection based on area
    if area < 1:  # Cities and small areas
        target_zoom = 9
        target_tiles = 10
        logging.info("📍 Small area detected (city/county)")
    elif area < 10:  # Small states (Maryland, Delaware)
        target_zoom = 8
        target_tiles = 20
        logging.info("🏛️ Small state detected")
    elif area < 50:  # Medium states (Florida, Indiana)
        target_zoom = 7
        target_tiles = 50
        logging.info("🏞️ Medium state detected")
    elif area < 150:  # Large states (California, Texas)
        target_zoom = 6
        target_tiles = 100
        logging.info("🌄 Large state detected")
    elif area < 500:  # Huge states (Alaska) or regions (Midwest)
        target_zoom = 5
        target_tiles = 200
        logging.info("🗻 Huge state/region detected")
    elif area < 2000:  # Multi-state regions
        target_zoom = 4
        target_tiles = 350
        logging.info("🌎 Multi-state region detected")
    else:  # Continental scale (CONUS, North America)
        target_zoom = 3
        target_tiles = 500
        logging.info("🌍 Continental scale detected")
    
    # Calculate actual tiles at target zoom
    try:
        nw_tile = mercantile.tile(bounds["west"], bounds["north"], target_zoom)
        se_tile = mercantile.tile(bounds["east"], bounds["south"], target_zoom)
        
        tile_count_x = se_tile.x - nw_tile.x + 1
        tile_count_y = se_tile.y - nw_tile.y + 1
        actual_tiles = tile_count_x * tile_count_y
        
        logging.info(f"🎯 Target zoom {target_zoom}: {tile_count_x} × {tile_count_y} = {actual_tiles} tiles")
        
        # ✅ ADAPTIVE: If actual tiles are way off from target, try adjacent zoom levels
        if actual_tiles < target_tiles * 0.5 and target_zoom > 3:
            # Too few tiles, zoom in one level
            test_zoom = target_zoom + 1
            test_nw = mercantile.tile(bounds["west"], bounds["north"], test_zoom)
            test_se = mercantile.tile(bounds["east"], bounds["south"], test_zoom)
            test_tiles = (test_se.x - test_nw.x + 1) * (test_se.y - test_nw.y + 1)
            
            if test_tiles <= 600:  # Don't exceed performance limit
                logging.info(f"⬆️ Zooming in: {test_tiles} tiles at zoom {test_zoom}")
                return test_zoom
        
        elif actual_tiles > target_tiles * 2 and target_zoom < 10:
            # Too many tiles, zoom out one level
            test_zoom = target_zoom - 1
            test_nw = mercantile.tile(bounds["west"], bounds["north"], test_zoom)
            test_se = mercantile.tile(bounds["east"], bounds["south"], test_zoom)
            test_tiles = (test_se.x - test_nw.x + 1) * (test_se.y - test_nw.y + 1)
            
            if test_tiles >= 6:  # Don't go below minimum
                logging.info(f"⬇️ Zooming out: {test_tiles} tiles at zoom {test_zoom}")
                return test_zoom
        
        logging.info(f"✅ Final: zoom {target_zoom} with {actual_tiles} tiles")
        logging.info(f"📊 Coverage: Each tile ≈ {area/actual_tiles:.2f} sq degrees")
        
        return target_zoom
        
    except Exception as e:
        logging.error(f"❌ Error calculating tiles: {e}")
        # Safe fallback
        if area < 10:
            return 8
        elif area < 100:
            return 7
        elif area < 500:
            return 6
        else:
            return 5

def create_tile_config(map_data: dict, user_query: str, date_info: dict = None) -> dict:
    """
    Create tile configuration
    Args:
        map_data: Map result with bounds
        user_query: Original user query
        date_info: Pre-extracted date info from extract_analysis_info() (optional)
    """
    import re
    import mercantile
    
    # ✅ Use pre-extracted date info if available
    if date_info:
        variable = date_info.get("variable", "Tair")
        date_str = date_info.get("date_str")
        
        # Parse date_str to get year, month, day
        if date_str:
            date_parts = date_str.split('-')
            year = int(date_parts[0])
            month = int(date_parts[1])
            day = int(date_parts[2]) if len(date_parts) > 2 else None
            
            logging.info(f"🗓️ Using pre-extracted date info: {date_str}, {variable}")
        else:
            return {"error": "No date in extracted info"}
    else:
        # Fall back to query parsing
        year_match = re.search(r'(20\d{2})', user_query)
        if not year_match:
            return {"error": "No year specified in query"}
        year = int(year_match.group(1))
        
        month_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)', user_query.lower())
        if not month_match:
            return {"error": "No month specified in query"}
        month_names = ['january','february','march','april','may','june','july','august','september','october','november','december']
        month = month_names.index(month_match.group(1)) + 1
        
        variable = 'Tair'  # Default
        if any(word in user_query.lower() for word in ['precipitation', 'rain', 'rainfall']):
            variable = 'Rainf'
        elif any(word in user_query.lower() for word in ['drought', 'spi']):
            variable = 'SPI3'
        
        # For daily variables, require day specification
        day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', user_query)
        if variable != 'SPI3' and (not day_match or not (1 <= int(day_match.group(1)) <= 31)):
            return {"error": "No valid day specified in query"}
        day = int(day_match.group(1)) if day_match else None
    
    # Build date_str if not already set
    if not date_info or not date_str:
        if variable == 'SPI3':
            date_str = f"{year}-{month:02d}"
        else:
            date_str = f"{year}-{month:02d}-{day:02d}"
    
    # Get bounds from map data
    bounds = map_data.get("bounds", {})
    if not bounds:
        logging.error("❌ No bounds provided in map_data")
        return {"error": "No geographic bounds available"}
    
    north = float(bounds.get("north"))
    south = float(bounds.get("south"))
    east = float(bounds.get("east"))
    west = float(bounds.get("west"))
    
    logging.info(f"🗺️ Creating tiles for: N={north:.2f}, S={south:.2f}, W={west:.2f}, E={east:.2f}")

    # ✅ FIXED: Get the correct colormap for the variable
    variable_cmaps = {
        'Tair': 'RdYlBu_r',
        'Rainf': 'Blues',
        'SPI3': 'RdBu',
        'Qair': 'BrBG',
        'PSurf': 'viridis',
        'Wind_Speed': 'viridis'
    }
    cmap = variable_cmaps.get(variable, 'viridis')

    # Calculate actual data range for this region
    try:
        from .weather_tool import (
            load_specific_date_kerchunk,
            load_specific_month_spi_kerchunk,
            get_account_key,
            ACCOUNT_NAME
        )
        
        account_key = get_account_key()
        
        if variable == 'SPI3':
            ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, month)
            data = ds[variable].sel(
                latitude=builtins.slice(south, north),
                longitude=builtins.slice(west, east)
            )
            region_vmin, region_vmax = -2.5, 2.5
        else:
            ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
            data = ds[variable].sel(
                lat=builtins.slice(south, north),
                lon=builtins.slice(west, east)
            )
            
            # Process the data
            if variable == 'Tair':
                data = data.mean(dim='time') - 273.15
            elif variable == 'Rainf':
                data = data.sum(dim='time')
            else:
                data = data.mean(dim='time')
            
            if hasattr(data, 'squeeze'):
                data = data.squeeze()
            
            valid_data = data.values[np.isfinite(data.values)]
            if len(valid_data) > 0:
                region_vmin, region_vmax = np.percentile(valid_data, [2, 98])
                
                if abs(region_vmax - region_vmin) < 0.1:
                    center = (region_vmin + region_vmax) / 2
                    region_vmin = center - 1.0
                    region_vmax = center + 1.0
            else:
                if variable == 'Tair':
                    region_vmin, region_vmax = -10, 30
                elif variable == 'Rainf':
                    region_vmin, region_vmax = 0, 50
                else:
                    region_vmin, region_vmax = 0, 100
        
        ds.close()
        logging.info(f"🎨 Region-specific scale: {region_vmin:.2f} to {region_vmax:.2f}, cmap={cmap}")
        
    except Exception as scale_error:
        logging.error(f"❌ Failed to calculate region scale: {scale_error}")
        if variable == 'SPI3':
            region_vmin, region_vmax = -2.5, 2.5
        elif variable == 'Tair':
            region_vmin, region_vmax = -10, 30
        elif variable == 'Rainf':
            region_vmin, region_vmax = 0, 50
        else:
            region_vmin, region_vmax = 0, 100
    
    # ✅ USE AREA-BASED ZOOM - DO NOT OVERRIDE IT
    zoom = determine_optimal_zoom_level(bounds)
    
    # Generate tile list using the calculated zoom
    nw_tile = mercantile.tile(west, north, zoom)
    se_tile = mercantile.tile(east, south, zoom)
    
    tile_count_x = se_tile.x - nw_tile.x + 1
    tile_count_y = se_tile.y - nw_tile.y + 1
    total_tiles = tile_count_x * tile_count_y
    
    logging.info(f"🎯 Final tile grid: {tile_count_x} × {tile_count_y} = {total_tiles} tiles at zoom {zoom}")
    
    # ✅ FIXED: Generate tile list with cmap parameter
    tile_list = []
    for x in range(nw_tile.x, se_tile.x + 1):
        for y in range(nw_tile.y, se_tile.y + 1):
            tile_bounds = mercantile.bounds(mercantile.Tile(x, y, zoom))
            
            tile_list.append({
                "z": zoom,
                "x": x,
                "y": y,
                "url": f"http://localhost:8000/api/tiles/{variable}/{date_str}/{zoom}/{x}/{y}.png?vmin={region_vmin}&vmax={region_vmax}&cmap={cmap}",
                "bounds": {
                    "north": tile_bounds.north,
                    "south": tile_bounds.south,
                    "east": tile_bounds.east,
                    "west": tile_bounds.west
                }
            })
    
    logging.info(f"✅ Generated {len(tile_list)} tiles: X={nw_tile.x}-{se_tile.x}, Y={nw_tile.y}-{se_tile.y} (256x256 each)")
    
    return {
        "tile_url": f"http://localhost:8000/api/tiles/{variable}/{date_str}/{{z}}/{{x}}/{{y}}.png?vmin={region_vmin}&vmax={region_vmax}&cmap={cmap}",
        "variable": variable,
        "date": date_str,
        "zoom": zoom,
        "min_zoom": max(3, zoom - 1),
        "max_zoom": min(10, zoom + 2),
        "tile_size": 256,
        "tile_list": tile_list,
        "region_bounds": {"north": north, "south": south, "east": east, "west": west},
        "tile_count": len(tile_list),
        "color_scale": {
            "vmin": float(region_vmin),
            "vmax": float(region_vmax),
            "cmap": cmap,  # ✅ FIXED: Include cmap in color_scale
            "variable": variable
        }
    }

def wrap_with_geo_overlay(static_url: str, original_query: str) -> dict:
    """
    Produce a unified response structure containing:
    - original static map URL (static_url)
    - overlay_url (same as static for now; future: transparent variant)
    - minimal GeoJSON sampling placeholder (empty FeatureCollection)
    - default map_config (frontend can refine)
    """
    logging.info("🌐 Adding unified overlay + geojson wrapper to static visualization")
    geojson = {
        "type": "FeatureCollection",
        "features": []
    }
    map_config = {
        "style": "satellite",
        "overlay_mode": True,
        "center": [ -98.0, 39.0 ],  # Fallback CONUS center
        "zoom": 5
    }
    return {
        "static_url": static_url,
        "overlay_url": None,  # distinguish that we lack a transparent overlay
        "geojson": geojson,
        "bounds": None,
        "map_config": map_config,
        "original_query": original_query
    }

def normalize_map_result_dict(raw: dict, original_query: str) -> dict:
    """Guarantee required keys for map dict returned by generated code."""
    static_url = raw.get("static_url")
    overlay_url = raw.get("overlay_url") or raw.get("transparent_url")
    # fallback: if only one provided treat as both
    if overlay_url is None and static_url:
        overlay_url = static_url
    if static_url is None and overlay_url:
        static_url = overlay_url
    geojson = raw.get("geojson") or {"type":"FeatureCollection","features":[]}
    bounds = raw.get("bounds") or {}
    map_config = raw.get("map_config") or {
        "center": bounds_center(bounds),
        "zoom": 6,
        "style": "satellite",
        "overlay_mode": True
    }
    # Fill center if missing
    if "center" not in map_config or not map_config["center"]:
        map_config["center"] = bounds_center(bounds)
    if "overlay_mode" not in map_config:
        map_config["overlay_mode"] = True
    return {
        "static_url": static_url,
        "overlay_url": overlay_url,
        "geojson": geojson,
        "bounds": bounds,
        "map_config": map_config,
        "original_query": original_query
    }

def build_temperature_data(geojson: dict, target_max_points: int = 2500) -> list:
    """Build temperature_data array from geojson features"""
    results = []
    if not geojson or geojson.get("type") != "FeatureCollection":
        return results
    features = geojson.get("features", [])
    total = len(features)
    if total == 0:
        return results
    # Adaptive stride
    if total > target_max_points:
        stride = max(1, int(total / target_max_points))
    else:
        stride = 1
    min_val = None
    max_val = None
    min_feat = None
    max_feat = None
    for idx, f in enumerate(features):
        if idx % stride != 0:
            # Still track min/max
            props = f.get("properties", {}) or {}
            v = props.get("value") or props.get("spi") or props.get("temperature")
            try:
                fv = float(v)
                if (min_val is None) or (fv < min_val):
                    min_val, min_feat = fv, f
                if (max_val is None) or (fv > max_val):
                    max_val, max_feat = fv, f
            except:
                pass
            continue
        geom = f.get("geometry", {})
        if geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        props = f.get("properties", {}) or {}
        val = props.get("value")
        if val is None:
            val = props.get("spi")
        if val is None:
            val = props.get("temperature")
        if val is None:
            continue
        try:
            val = float(val)
        except:
            continue
        results.append({
            "latitude": lat,
            "longitude": lon,
            "value": val,
            "originalValue": val,
            "location": f"{lat:.2f}, {lon:.2f}"
        })
    def add_extreme(feat):
        if not feat:
            return
        geom = feat.get("geometry", {})
        if geom.get("type") != "Point":
            return
        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            return
        lon, lat = float(coords[0]), float(coords[1])
        props = feat.get("properties", {}) or {}
        v = props.get("value") or props.get("spi") or props.get("temperature")
        try:
            fv = float(v)
        except:
            return
        key = (round(lat, 6), round(lon, 6))
        if all((round(r["latitude"],6), round(r["longitude"],6)) != key for r in results):
            results.append({
                "latitude": lat,
                "longitude": lon,
                "value": fv,
                "originalValue": fv,
                "location": f"{lat:.2f}, {lon:.2f}"
            })
    add_extreme(min_feat)
    add_extreme(max_feat)
    return results

def bounds_center(bounds: dict):
    """Calculate center point from bounds"""
    try:
        return [
            float((bounds.get("east")+bounds.get("west"))/2),
            float((bounds.get("north")+bounds.get("south"))/2)
        ]
    except Exception:
        return [-98.0, 39.0]

def should_use_tiles(user_query: str, map_data: dict) -> bool:
    """
    ALWAYS use tiles - unified approach for all map queries
    """
    bounds = map_data.get("bounds", {})
    if not bounds:
        logging.warning("❌ No bounds in map_data - cannot use tiles")
        return False
    
    logging.info("✅ Using tiles for ALL map queries (unified approach)")
    return True

def extract_agent_text_response(thread_id: str) -> str:
    """Extract the most recent assistant message from the thread"""
    try:
        messages = project_client.agents.messages.list(thread_id=thread_id)
        messages_list = list(messages)
        
        for message in messages_list:
            if message.role == "assistant":
                if message.content and len(message.content) > 0:
                    content_block = message.content[0]
                    if hasattr(content_block, 'text'):
                        return content_block.text.value
                    elif hasattr(content_block, 'value'):
                        return content_block.value
                    else:
                        return str(content_block)
        
        return "Hello! I'm the NLDAS-3 Weather Assistant. I can help you with weather data queries, maps, and analysis. What would you like to know?"
        
    except Exception as e:
        logging.error(f"❌ Error extracting text response: {e}", exc_info=True)
        return "Hello! I'm here to help with weather data. What would you like to explore?"

def extract_analysis_info(query: str, result: dict, memory_context: str = "") -> dict:
    """
    Extract variable, region, and date from result metadata FIRST, then query, then memory
    
    Priority order:
    1. Result metadata (what was actually used to create the map)
    2. Query parsing (explicit request)
    3. Memory context (for "same" queries)
    
    Args:
        query: Current user query
        result: Result dict from code execution (should contain metadata)
        memory_context: Recent memory context string
    """
    import re
    
    query_lower = query.lower()
    
    # ✅ PRIORITY 1: Extract from result metadata (most reliable - what was actually used)
    variable = None
    date_str = None
    region = "unknown"
    
    if result and "metadata" in result:
        metadata = result["metadata"]
        variable = metadata.get("variable")
        date_str = metadata.get("date")
        region = metadata.get("region", "unknown")
        
        if variable:
            logging.info(f"✅ Using metadata from result: variable={variable}, date={date_str}, region={region}")
            return {
                "variable": variable,
                "region": region,
                "date_str": date_str
            }
    
    # Fallback: Try to extract from color_scale if metadata not present
    if not variable and result:
        color_scale = result.get("color_scale", {})
        if color_scale and "variable" in color_scale:
            variable = color_scale["variable"]
            logging.info(f"📊 Extracted variable from color_scale: {variable}")
    
    # ✅ PRIORITY 2: Check memory for "same" queries
    if not variable and any(word in query_lower for word in ['same', 'similar', 'that', 'this']):
        if 'SPI3' in memory_context or 'drought' in memory_context.lower():
            variable = "SPI3"
            logging.info("📝 Extracted variable from memory: SPI3 (drought)")
        elif 'Rainf' in memory_context or 'precipitation' in memory_context.lower():
            variable = "Rainf"
            logging.info("📝 Extracted variable from memory: Rainf (precipitation)")
        elif 'Tair' in memory_context or 'temperature' in memory_context.lower():
            variable = "Tair"
            logging.info("📝 Extracted variable from memory: Tair (temperature)")
    
    # ✅ PRIORITY 3: Parse from current query
    if not variable:
        if any(word in query_lower for word in ['drought', 'spi']):
            variable = "SPI3"
            logging.info("📝 Extracted variable from query: SPI3")
        elif any(word in query_lower for word in ['precipitation', 'rain', 'rainfall', 'precip']):
            variable = "Rainf"
            logging.info("📝 Extracted variable from query: Rainf (precipitation)")
        elif any(word in query_lower for word in ['temperature', 'temp']):
            variable = "Tair"
            logging.info("📝 Extracted variable from query: Tair")
    
    # ✅ VALIDATE: If variable is still None, return error
    if not variable:
        logging.error(f"❌ Could not detect variable type from query: {query}")
        return {
            "error": "Could not determine which weather variable you want. Please specify: temperature, precipitation, or drought/SPI"
        }
    
    # ✅ Extract region (if not already from metadata)
    if region == "unknown":
        regions = {
            'michigan': 'michigan',
            'florida': 'florida',
            'california': 'california',
            'maryland': 'maryland',
            'texas': 'texas',
            'alaska': 'alaska',
            'hope': 'alaska',  # Hope is a city in Alaska
        }
        for key, value in regions.items():
            if key in query_lower:
                region = value
                break
    
    # ✅ Extract date (if not already from metadata)
    if not date_str:
        year = None
        month = None
        day = None
        
        if any(word in query_lower for word in ['same', 'similar', 'that', 'this']):
            # Extract date from memory (format: "2023-06-15" or "2023-06")
            memory_date_match = re.search(r'on (\d{4}-\d{2}(?:-\d{2})?)', memory_context)
            if memory_date_match:
                date_str = memory_date_match.group(1)
                logging.info(f"📅 Extracted date from memory: {date_str}")
        
        # If not found in memory, extract from query
        if not date_str:
            year_match = re.search(r'(20\d{2})', query)
            year = int(year_match.group(1)) if year_match else 2023
            
            month_names = ['january','february','march','april','may','june','july','august','september','october','november','december']
            month_match = re.search(r'(' + '|'.join(month_names) + ')', query_lower)
            month = month_names.index(month_match.group(1)) + 1 if month_match else 6
            
            if variable != "SPI3":
                day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', query)
                day = int(day_match.group(1)) if day_match else 15
            
            # Build date string
            if variable == "SPI3":
                date_str = f"{year}-{month:02d}"
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
    
    logging.info(f"📊 Final extracted info: variable={variable}, region={region}, date={date_str}")
    
    return {
        "variable": variable,
        "region": region,
        "date_str": date_str
    }

def handle_chat_request(data):
    """Handle chat requests with memory, timing, enhanced error handling, and analysis detection"""
    # ===== PERFORMANCE TIMING: Start =====
    start_total = time.time()
    times = {}
    
    try:
        # ===== VALIDATION =====
        t1 = time.time()
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        logging.info(f"Processing chat request: {user_query}")
        
        # Get user_id from request data
        user_id = data.get("user_id", f"anonymous_{hash(user_query) % 10000}")
        logging.info(f"👤 User ID: {user_id}")

        # ===== MEMORY RETRIEVAL =====
        t2 = time.time()

        # ✅ DEBUG: Check if this is a truly new user
        all_user_memories = memory_manager.get_all(user_id)
        memory_count = len(all_user_memories) if isinstance(all_user_memories, list) else len(all_user_memories.get('results', []))
        logging.info(f"📊 User {user_id[:8]}... has {memory_count} total memories in database")

        # Retrieve memory context BEFORE sending to agent
        recent_memories = memory_manager.recent_context(user_id, limit=3)
        relevant_memories = memory_manager.search(user_query, user_id, limit=3)

        logging.info(f"📚 Recent memories retrieved: {len(recent_memories)}")
        logging.info(f"🔍 Relevant memories retrieved: {len(relevant_memories)}")

        # ✅ Validate memory isolation
        if recent_memories or relevant_memories:
            # Check that all retrieved memories actually belong to this user
            for mem in relevant_memories:
                if isinstance(mem, dict):
                    mem_user = mem.get('user_id', '')
                    if mem_user and mem_user != user_id:
                        logging.error(f"🚨 MEMORY LEAK: Retrieved memory from {mem_user[:8]}... for user {user_id[:8]}...")
        
        # Build enhanced query with memory context
        memory_context_str = ""
        if recent_memories or relevant_memories:
            memory_context_str = "\n\n🧠 Recent context from your previous queries:\n"
            
            if recent_memories:
                memory_context_str += "Recent conversations:\n"
                for mem in recent_memories[:2]:
                    memory_context_str += f"- {mem}\n"
            
            if relevant_memories:
                memory_context_str += "\nRelevant previous analyses:\n"
                for mem in relevant_memories[:2]:
                    mem_text = mem.get("memory", "")
                    if mem_text:
                        memory_context_str += f"- {mem_text}\n"

        enhanced_query = user_query + memory_context_str
        times['memory_retrieval'] = time.time() - t2
            
        # ===== THREAD CREATION =====
        t3 = time.time()
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")
        times['thread_creation'] = time.time() - t3
        
        # ===== MESSAGE CREATION =====
        t4 = time.time()
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=enhanced_query
        )
        logging.info(f"Created message: {message.id}")
        times['message_creation'] = time.time() - t4
        
        # ===== RUN CREATION =====
        t5 = time.time()
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        logging.info(f"Started run: {run.id}")
        times['run_creation'] = time.time() - t5
        
        # ===== ANALYSIS QUERY DETECTION =====
        t6 = time.time()
        analysis_keywords = [
            'most significant', 'most extreme', 'hottest', 'coldest', 
            'warmest', 'wettest', 'driest', 'highest', 'lowest', 
            'top', 'worst', 'best', 'find', 'where are'
        ]
        is_analysis_query = any(phrase in user_query.lower() for phrase in analysis_keywords)
        times['analysis_detection'] = time.time() - t6
        
        if is_analysis_query:
            # Direct analysis timing
            t7 = time.time()
            logging.info(f"🔍 Detected analysis query - using direct analysis function")
            try:
                from .dynamic_code_generator import analyze_extreme_regions
                analysis_result = analyze_extreme_regions(user_query)
                times['direct_analysis'] = time.time() - t7
                times['total'] = time.time() - start_total
                
                logging.info(f"⏱️  ANALYSIS TIMING: {json.dumps(times, indent=2)}")
                
                if analysis_result.get("status") == "success":
                    result_value = analysis_result.get("result")
                    
                    # Store in memory
                    memory_manager.add(
                        f"Query: {user_query}\nAnalysis: Found {len(result_value.get('regions', []))} extreme regions",
                        user_id,
                        {"type": "analysis", "query": user_query}
                    )
                    
                    # Return the complete structured analysis response
                    return make_json_serializable({
                        "status": "success",
                        "content": f"Analysis completed: Found {len(result_value.get('regions', []))} extreme regions",
                        "analysis_data": analysis_result,
                        "type": "analysis_complete",
                        "regions": result_value.get("regions", []),
                        "geojson": result_value.get("geojson", {}),
                        "bounds": result_value.get("bounds", {}),
                        "map_config": result_value.get("map_config", {}),
                        "variable": result_value.get("variable"),
                        "analysis_type": result_value.get("analysis_type"),
                        "temperature_data": build_temperature_data(result_value.get("geojson", {})),
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "user_id": user_id,
                        "timing_breakdown": times
                    })
                else:
                    return make_json_serializable({
                        "status": "error",
                        "content": f"Analysis failed: {analysis_result.get('error', 'Unknown error')}",
                        "type": "analysis_error",
                        "user_id": user_id,
                        "timing_breakdown": times
                    })
                    
            except Exception as analysis_error:
                times['direct_analysis_failed'] = time.time() - t7
                logging.error(f"❌ Direct analysis failed: {analysis_error}")
                logging.info("🔄 Falling back to agent-based analysis")
        
        # ===== ENHANCED EXECUTION LOOP =====
        t8 = time.time()
        max_iterations = 20
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        
        start_time = time.time()
        max_total_time = 120  # 2 minutes total
        max_in_progress_time = 8  # Max time to stay in "in_progress"
        last_status_change = start_time
        in_progress_count = 0
        
        while iteration < max_iterations:
            iteration += 1
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            logging.info(f"🔄 Run status: {run.status} (iteration {iteration}/{max_iterations}, elapsed: {elapsed_time:.1f}s)")
            
            # Overall timeout check
            if elapsed_time > max_total_time:
                logging.warning(f"⏰ TIMEOUT: Exceeded {max_total_time}s")
                break
            
            # ===== ENHANCED ERROR HANDLING: Stuck Detection =====
            if run.status == "in_progress":
                in_progress_count += 1
                time_in_progress = current_time - last_status_change
                
                # If stuck in "in_progress" too long, try to force action
                if time_in_progress > max_in_progress_time:
                    logging.warning(f"⚠️ Stuck in 'in_progress' for {time_in_progress:.1f}s. Attempting to force completion...")
                    
                    # Try to cancel and restart the run
                    try:
                        project_client.agents.runs.cancel(thread_id=thread.id, run_id=run.id)
                        time.sleep(1)
                        
                        # Create a new, more direct message
                        direct_message = project_client.agents.messages.create(
                            thread_id=thread.id,
                            role="user",
                            content="EXECUTE FUNCTION NOW! Call execute_custom_code immediately."
                        )
                        
                        # Start a new run
                        run = project_client.agents.runs.create(
                            thread_id=thread.id,
                            agent_id=text_agent_id
                        )
                        
                        last_status_change = time.time()
                        in_progress_count = 0
                        logging.info("🔄 Restarted run after being stuck")
                        
                    except Exception as restart_error:
                        logging.error(f"❌ Failed to restart run: {restart_error}")
                        break
            else:
                # Status changed, reset counters
                if run.status != getattr(handle_chat_request, '_last_status', None):
                    last_status_change = current_time
                    in_progress_count = 0
                    handle_chat_request._last_status = run.status
            
            # ===== CASE 1: COMPLETED =====
            if run.status == "completed":
                logging.info("✅ Run completed")
                
                if not custom_code_executed:
                    # Text-only response
                    text_response = extract_agent_text_response(thread.id)
                    
                    # Store text response in memory
                    memory_manager.add(
                        f"Query: {user_query}\nResponse: {text_response}",
                        user_id,
                        {"type": "conversation", "query": user_query}
                    )
                    logging.info(f"💾 Stored conversation in memory for user {user_id}")
                    
                    times['execution_loop'] = time.time() - t8
                    times['total'] = time.time() - start_total
                    
                    logging.info(f"⏱️  TIMING BREAKDOWN: {json.dumps(times, indent=2)}")
                    
                    response = {
                        "status": "success",
                        "content": text_response,
                        "type": "text_response",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "user_id": user_id,
                        "timing_breakdown": times
                    }
                    
                    return make_json_serializable(response)
                else:
                    # Code was executed
                    times['execution_loop'] = time.time() - t8
                    times['total'] = time.time() - start_total
                    
                    logging.info(f"⏱️  TIMING BREAKDOWN: {json.dumps(times, indent=2)}")
                    
                    response = {
                        "status": "success",
                        "content": "Analysis completed",
                        "type": "code_execution_complete",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "analysis_data": analysis_data,
                        "user_id": user_id,
                        "timing_breakdown": times
                    }
                    
                    return make_json_serializable(response)
            
            # ===== CASE 2: REQUIRES_ACTION =====
            elif run.status == "requires_action":
                logging.info("🛠️ Run requires action - processing tool calls")
                
                if run.required_action and run.required_action.submit_tool_outputs:
                    tool_calls = run.required_action.submit_tool_outputs.tool_calls
                    logging.info(f"🔧 Processing {len(tool_calls)} tool call(s)")
                    
                    tool_outputs = []
                    
                    for tool_call in tool_calls:
                        if tool_call.function.name == "execute_custom_code":
                            try:
                                raw_arguments = tool_call.function.arguments
                                
                                if not raw_arguments or not raw_arguments.strip():
                                    logging.warning("⚠️ Empty arguments, using fallback")
                                    function_args = {
                                        "python_code": "result = 'Hello! I can help you with weather data analysis.'",
                                        "user_request": user_query
                                    }
                                else:
                                    function_args = json.loads(raw_arguments)
                                
                                # Pass user_id to code execution
                                function_args["user_id"] = user_id
                                
                                logging.info("🚀 Executing custom code...")
                                analysis_result = execute_custom_code(function_args)
                                custom_code_executed = True
                                analysis_data = analysis_result

                                # Handle result
                                if analysis_result.get("status") == "success":
                                    result_value = analysis_result.get("result")
                                    
                                    # Handle map results
                                    if isinstance(result_value, dict) and ("static_url" in result_value or "overlay_url" in result_value):
                                        logging.info("🗺️ Map result detected")
                                        
                                        # Extract analysis info
                                        extracted_info = extract_analysis_info(user_query, result_value, memory_context_str)

                                        # ✅ ONLY store if extraction succeeded
                                        if "error" not in extracted_info:
                                            memory_manager.add_structured_analysis(
                                                user_id=user_id,
                                                variable=extracted_info["variable"],
                                                region=extracted_info["region"],
                                                date_str=extracted_info["date_str"],
                                                bounds=result_value.get("bounds", {}),
                                                result_url=result_value.get("static_url"),
                                                color_range=result_value.get("color_scale")
                                            )
                                            logging.info(f"💾 Stored structured analysis memory for {user_id}")
                                        else:
                                            logging.warning(f"⚠️ Skipping memory storage due to extraction error: {extracted_info.get('error')}")
                                        
                                        # ✅ CRITICAL: Continue processing regardless of memory storage
                                        enriched = normalize_map_result_dict(result_value, user_query)
                                        enriched["temperature_data"] = build_temperature_data(enriched.get("geojson", {}))
                                        
                                        use_tiles = should_use_tiles(user_query, enriched)

                                        if use_tiles:
                                            # ✅ Only create tiles if we have valid metadata
                                            if "error" not in extracted_info:
                                                tile_config = create_tile_config(enriched, user_query, extracted_info)
                                            else:
                                                # Fallback: Try to create tile config without extracted_info
                                                logging.warning(f"⚠️ Creating tile config without extracted_info: {extracted_info.get('error')}")
                                                tile_config = create_tile_config(enriched, user_query, date_info=None)
                                            
                                            # Check if tile config failed
                                            if "error" in tile_config:
                                                logging.warning(f"⚠️ Tile generation failed: {tile_config['error']}")
                                                logging.info("📍 Falling back to static-only response")
                                                
                                                # Return static-only response
                                                tool_outputs.append({
                                                    "tool_call_id": tool_call.id,
                                                    "output": json.dumps({"status": "success", "completed": True})
                                                })
                                                
                                                project_client.agents.runs.submit_tool_outputs(
                                                    thread_id=thread.id,
                                                    run_id=run.id,
                                                    tool_outputs=tool_outputs
                                                )
                                                
                                                times['execution_loop'] = time.time() - t8
                                                times['total'] = time.time() - start_total
                                                
                                                logging.info(f"⏱️  TIMING BREAKDOWN: {json.dumps(times, indent=2)}")
                                                
                                                response = {
                                                    "status": "success",
                                                    "content": enriched.get("static_url", "Map generated"),
                                                    "static_url": enriched.get("static_url"),
                                                    "overlay_url": enriched.get("overlay_url"),
                                                    "geojson": enriched["geojson"],
                                                    "bounds": enriched["bounds"],
                                                    "map_config": enriched["map_config"],
                                                    "temperature_data": enriched["temperature_data"],
                                                    "type": "visualization_with_overlay",
                                                    "agent_id": text_agent_id,
                                                    "thread_id": thread.id,
                                                    "analysis_data": analysis_result,
                                                    "user_id": user_id,
                                                    "tile_error": tile_config.get('error'),
                                                    "timing_breakdown": times
                                                }
                                                
                                                return make_json_serializable(response)
                                            
                                            # Success - tiles generated
                                            tool_outputs.append({
                                                "tool_call_id": tool_call.id,
                                                "output": json.dumps({"status": "success", "completed": True})
                                            })
                                            
                                            project_client.agents.runs.submit_tool_outputs(
                                                thread_id=thread.id,
                                                run_id=run.id,
                                                tool_outputs=tool_outputs
                                            )
                                            
                                            times['execution_loop'] = time.time() - t8
                                            times['total'] = time.time() - start_total
                                            
                                            logging.info(f"⏱️  TIMING BREAKDOWN: {json.dumps(times, indent=2)}")
                                            
                                            response = {
                                                "status": "success",
                                                "content": enriched.get("static_url", "Interactive map generated"),
                                                "use_tiles": True,
                                                "tile_config": tile_config,
                                                "static_url": enriched.get("static_url"),
                                                "geojson": enriched["geojson"],
                                                "bounds": enriched["bounds"],
                                                "map_config": enriched["map_config"],
                                                "temperature_data": enriched["temperature_data"],
                                                "type": "visualization_with_tiles",
                                                "agent_id": text_agent_id,
                                                "thread_id": thread.id,
                                                "analysis_data": analysis_result,
                                                "user_id": user_id,
                                                "timing_breakdown": times
                                            }
                                            
                                            return make_json_serializable(response)
                                        
                                        else:
                                            # No tiles - static only
                                            tool_outputs.append({
                                                "tool_call_id": tool_call.id,
                                                "output": json.dumps({"status": "success", "completed": True})
                                            })
                                            
                                            project_client.agents.runs.submit_tool_outputs(
                                                thread_id=thread.id,
                                                run_id=run.id,
                                                tool_outputs=tool_outputs
                                            )
                                            
                                            times['execution_loop'] = time.time() - t8
                                            times['total'] = time.time() - start_total
                                            
                                            logging.info(f"⏱️  TIMING BREAKDOWN: {json.dumps(times, indent=2)}")
                                            
                                            response = {
                                                "status": "success",
                                                "content": enriched.get("static_url", "Map generated"),
                                                "static_url": enriched.get("static_url"),
                                                "overlay_url": enriched.get("overlay_url"),
                                                "geojson": enriched["geojson"],
                                                "bounds": enriched["bounds"],
                                                "map_config": enriched["map_config"],
                                                "temperature_data": enriched["temperature_data"],
                                                "type": "visualization_with_overlay",
                                                "agent_id": text_agent_id,
                                                "thread_id": thread.id,
                                                "analysis_data": analysis_result,
                                                "user_id": user_id,
                                                "timing_breakdown": times
                                            }
                                            
                                            return make_json_serializable(response)
                                    else:
                                        # Text result (not a map)
                                        memory_manager.add(
                                            f"Query: {user_query}\nResult: {str(result_value)[:200]}",
                                            user_id,
                                            {"type": "analysis", "query": user_query}
                                        )
                                        logging.info(f"💾 Stored text analysis in memory for {user_id}")
                                        
                                        tool_outputs.append({
                                            "tool_call_id": tool_call.id,
                                            "output": json.dumps({"status": "success", "result": str(result_value)})
                                        })
                                else:
                                    # Execution failed
                                    error_msg = analysis_result.get("error", "Unknown error")
                                    tool_outputs.append({
                                        "tool_call_id": tool_call.id,
                                        "output": json.dumps({"status": "error", "error": error_msg})
                                    })
                                    
                            except Exception as e:
                                logging.error(f"❌ Tool call error: {e}", exc_info=True)
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({"status": "error", "error": str(e)})
                                })
                    
                    # Submit tool outputs
                    try:
                        project_client.agents.runs.submit_tool_outputs(
                            thread_id=thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                        logging.info("✅ Tool outputs submitted")
                    except Exception as e:
                        logging.error(f"❌ Failed to submit tool outputs: {e}")
            
            # ===== CASE 3: FAILED/CANCELLED/EXPIRED =====
            elif run.status in ["failed", "cancelled", "expired"]:
                logging.error(f"❌ Run ended with status: {run.status}")
                times['execution_loop'] = time.time() - t8
                times['total'] = time.time() - start_total
                
                logging.info(f"⏱️  ERROR TIMING: {json.dumps(times, indent=2)}")
                
                response = {
                    "status": "error",
                    "content": f"Agent run {run.status}",
                    "type": f"run_{run.status}",
                    "agent_id": text_agent_id,
                    "thread_id": thread.id,
                    "user_id": user_id,
                    "timing_breakdown": times
                }
                
                return make_json_serializable(response)
            
            # ===== CASE 4: QUEUED/IN_PROGRESS =====
            elif run.status in ["queued", "in_progress"]:
                # Variable wait time based on status
                if run.status == "in_progress":
                    time.sleep(0.5)
                else:
                    time.sleep(0.3)
            
            # Refresh run status
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"❌ Error refreshing run: {e}")
                break
        
        # Final timeout response
        times['execution_loop'] = time.time() - t8
        times['total'] = time.time() - start_total
        elapsed_time = time.time() - start_time
        
        logging.error(f"❌ Agent completion without execution:")
        logging.error(f"   Final status: {run.status}")
        logging.error(f"   Iterations: {iteration}/{max_iterations}")
        logging.error(f"   Elapsed time: {elapsed_time:.1f}s")
        logging.info(f"⏱️  TIMEOUT TIMING: {json.dumps(times, indent=2)}")
        
        response = {
            "status": "timeout_failure",
            "content": f"Agent failed after {iteration} iterations ({elapsed_time:.1f}s). Status: {run.status}",
            "type": "timeout",
            "agent_id": text_agent_id,
            "thread_id": thread.id,
            "user_id": user_id,
            "debug": {
                "iterations": iteration,
                "final_status": run.status,
                "elapsed_time": elapsed_time
            },
            "timing_breakdown": times
        }
        
        return make_json_serializable(response)
        
    except Exception as e:
        times['total'] = time.time() - start_total
        logging.error(f"❌ Chat request error: {e}", exc_info=True)
        logging.info(f"⏱️  ERROR TIMING: {json.dumps(times, indent=2)}")
        
        response = {
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__,
            "user_id": data.get("user_id", "unknown"),
            "timing_breakdown": times
        }
        
        return make_json_serializable(response)

def make_json_serializable(obj, _seen=None):
    """Enhanced JSON serialization that handles all Python types including circular references"""
    import types
    from datetime import datetime, date
    
    # Track seen objects to prevent infinite recursion
    if _seen is None:
        _seen = set()
    
    # Check if we've seen this object before (circular reference)
    obj_id = id(obj)
    if obj_id in _seen:
        return f"<circular reference to {type(obj).__name__}>"
    
    # Add basic types that don't need recursion tracking
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    
    # Mark this object as seen
    _seen.add(obj_id)
    
    try:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: make_json_serializable(v, _seen) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [make_json_serializable(item, _seen) for item in obj]
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, types.MappingProxyType):
            return {k: make_json_serializable(v, _seen) for k, v in obj.items()}
        elif hasattr(obj, '__dict__'):
            # Avoid infinite recursion on complex objects
            try:
                return {k: make_json_serializable(v, _seen) for k, v in obj.__dict__.items() if not k.startswith('_')}
            except:
                return str(obj)
        elif hasattr(obj, '_asdict'):  # namedtuple
            return make_json_serializable(obj._asdict(), _seen)
        else:
            return str(obj)
    except Exception as e:
        return f"<serialization error: {type(obj).__name__}>"
    finally:
        # Remove from seen set after processing
        _seen.discard(obj_id)