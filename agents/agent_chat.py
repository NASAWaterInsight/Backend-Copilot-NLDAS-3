# agents/agent_chat.py - Fixed version with better timeout and error handling
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
from .dynamic_code_generator import execute_custom_code
import numpy as np
import builtins
import mercantile

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
    """Handle different versions of the Azure AI SDK"""
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

# In your agent_chat.py, replace the existing create_tile_config function:

def determine_optimal_zoom_level(bounds: dict) -> int:
    """
    Area-based zoom selection for optimal tile count
    
    Strategy: Linear scaling with area
    - Target: 2.5 tiles per 100 square degrees
    - Min: 6 tiles (small regions)
    - Max: 300 tiles (continental scale)
    
    Examples:
    - Maryland (8 sq°): ~6 tiles at zoom 8
    - Florida (56 sq°): ~8 tiles at zoom 7
    - California (420 sq°): ~12 tiles at zoom 7
    - Alaska (840 sq°): ~24 tiles at zoom 6
    - CONUS (8000 sq°): ~200 tiles at zoom 5
    """
    import mercantile
    
    lat_span = bounds["north"] - bounds["south"]
    lng_span = bounds["east"] - bounds["west"]
    area = lat_span * lng_span
    
    logging.info(f"🗺️ Region bounds: N={bounds['north']:.2f}, S={bounds['south']:.2f}, E={bounds['east']:.2f}, W={bounds['west']:.2f}")
    logging.info(f"📐 Region area: {area:.2f} sq degrees ({lat_span:.2f}° × {lng_span:.2f}°)")
    
    # HARDCODED: California override (if you still want this)
    if (31 <= bounds["south"] <= 33 and 
        41 <= bounds["north"] <= 43 and 
        -126 <= bounds["west"] <= -124 and 
        -115 <= bounds["east"] <= -113):
        logging.info("🗺️ Detected California - using hardcoded zoom 7")
        return 7
    
    # LINEAR SCALING: 2.5 tiles per 100 square degrees
    TILES_PER_100_SQ_DEGREES = 2.5
    target_tiles = (area / 100.0) * TILES_PER_100_SQ_DEGREES
    
    # Apply constraints
    MIN_TILES = 6
    MAX_TILES = 300
    target_tiles = max(MIN_TILES, min(MAX_TILES, target_tiles))
    
    logging.info(f"🎯 Target tiles: {target_tiles:.0f} (formula: {area:.1f}/100 × {TILES_PER_100_SQ_DEGREES})")
    
    # Find zoom level that produces closest tile count
    best_zoom = 6
    best_diff = float('inf')
    best_count = 0
    
    for zoom in range(3, 11):
        try:
            nw_tile = mercantile.tile(bounds["west"], bounds["north"], zoom)
            se_tile = mercantile.tile(bounds["east"], bounds["south"], zoom)
            
            tile_count_x = se_tile.x - nw_tile.x + 1
            tile_count_y = se_tile.y - nw_tile.y + 1
            total_tiles = tile_count_x * tile_count_y
            
            diff = abs(total_tiles - target_tiles)
            
            logging.info(f"  Zoom {zoom}: {tile_count_x} × {tile_count_y} = {total_tiles} tiles (diff from target: {diff:.0f})")
            
            if diff < best_diff:
                best_diff = diff
                best_zoom = zoom
                best_count = total_tiles
                
        except Exception as e:
            logging.warning(f"  Zoom {zoom}: Failed to calculate tiles - {e}")
            continue
    
    logging.info(f"✅ Selected zoom {best_zoom}: {best_count} tiles (target was {target_tiles:.0f})")
    logging.info(f"📊 Coverage: Each tile ≈ {area/best_count:.1f} sq degrees")
    
    return best_zoom                    # City level


def create_tile_config(map_data: dict, user_query: str) -> dict:
    """
    Create tile configuration with REGION-SPECIFIC global scale and DYNAMIC zoom
    Uses area-based scaling - larger regions get MORE tiles at appropriate zoom
    """
    import re
    import mercantile
    
    # Extract date and variable (existing code)
    year_match = re.search(r'(20\d{2})', user_query)
    year = int(year_match.group(1)) if year_match else 2023
    
    month_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)', user_query.lower())
    month_names = ['january','february','march','april','may','june','july','august','september','october','november','december']
    month = month_names.index(month_match.group(1)) + 1 if month_match else 5
    
    day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', user_query)
    day = int(day_match.group(1)) if day_match and 1 <= int(day_match.group(1)) <= 31 else 12
    
    variable = 'Tair'  # Default
    if any(word in user_query.lower() for word in ['precipitation', 'rain', 'rainfall']):
        variable = 'Rainf'
    elif any(word in user_query.lower() for word in ['drought', 'spi']):
        variable = 'SPI3'
        date_str = f"{year}-{month:02d}"  # SPI is monthly
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
        logging.info(f"🎨 Region-specific scale: {region_vmin:.2f} to {region_vmax:.2f}")
        
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
    
    # ❌ REMOVED: The old "smart tile count management" that was reducing tiles
    # We trust the area-based calculation from determine_optimal_zoom_level()
    
    # Generate tile list
    tile_list = []
    for x in range(nw_tile.x, se_tile.x + 1):
        for y in range(nw_tile.y, se_tile.y + 1):
            tile_bounds = mercantile.bounds(mercantile.Tile(x, y, zoom))
            
            tile_list.append({
                "z": zoom,
                "x": x,
                "y": y,
                "url": f"http://localhost:8000/api/tiles/{variable}/{date_str}/{zoom}/{x}/{y}.png?vmin={region_vmin}&vmax={region_vmax}",
                "bounds": {
                    "north": tile_bounds.north,
                    "south": tile_bounds.south,
                    "east": tile_bounds.east,
                    "west": tile_bounds.west
                }
            })
    
    logging.info(f"✅ Generated {len(tile_list)} tiles: X={nw_tile.x}-{se_tile.x}, Y={nw_tile.y}-{se_tile.y} (256x256 each)")
    
    return {
        "tile_url": f"http://localhost:8000/api/tiles/{variable}/{date_str}/{{z}}/{{x}}/{{y}}.png?vmin={region_vmin}&vmax={region_vmax}",
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
            "variable": variable
        }
    }

def extract_agent_text_response(thread_id: str) -> str:
    """
    Extract the most recent assistant message from the thread.
    This is called when the run status is 'completed' with no tool calls.
    """
    try:
        # List messages in the thread
        messages = project_client.agents.messages.list(thread_id=thread_id)
        messages_list = list(messages)
        
        # Find the most recent assistant message
        for message in messages_list:
            if message.role == "assistant":
                if message.content and len(message.content) > 0:
                    content_block = message.content[0]
                    
                    # Handle different content types
                    if hasattr(content_block, 'text'):
                        return content_block.text.value
                    elif hasattr(content_block, 'value'):
                        return content_block.value
                    else:
                        return str(content_block)
        
        # No assistant message found
        return "I'm here to help! What would you like to know?"
        
    except Exception as e:
        logging.error(f"❌ Error extracting text response: {e}", exc_info=True)
        return "I encountered an issue. Please try again."


def handle_chat_request(data_or_query, thread_id: str = None):
    """
    COMPATIBLE: Handles both old data dict format and new query string format
    """
    try:
        # Handle both call formats
        if isinstance(data_or_query, dict):
            # Old format: handle_chat_request({"input": "query"})
            user_query = data_or_query.get("input", data_or_query.get("query", "Tell me about NLDAS-3 data"))
            thread_id = data_or_query.get("thread_id")
        else:
            # New format: handle_chat_request("query", thread_id)
            user_query = data_or_query

        logging.info(f"📨 Received query: {user_query}")
        
        # Create or reuse thread
        if thread_id:
            thread = type('Thread', (), {'id': thread_id})()
            logging.info(f"♻️ Reusing thread: {thread_id}")
        else:
            # ✅ FIXED: Use correct SDK method
            thread = project_client.agents.threads.create()
            logging.info(f"🆕 Created new thread: {thread.id}")
        
        # Create message
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_query
        )
        
        # Create run
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        
        logging.info(f"🏃 Started run: {run.id} with status: {run.status}")
        
        # FIXED: Main loop now handles 'completed' status properly
        max_iterations = 20
        iteration = 0
        start_time = time.time()
        max_total_time = 60  # 60 seconds timeout
        
        # Track if we executed any code
        custom_code_executed = False
        analysis_data = None
        
        while iteration < max_iterations:
            iteration += 1
            elapsed_time = time.time() - start_time
            
            logging.info(f"🔄 Iteration {iteration}/{max_iterations}: status={run.status}, elapsed={elapsed_time:.1f}s")
            
            # Check overall timeout
            if elapsed_time > max_total_time:
                logging.warning(f"⏰ TIMEOUT: Exceeded {max_total_time}s")
                break
            
            # ===== CASE 1: COMPLETED (Text-only response) =====
            if run.status == "completed":
                logging.info("✅ Run completed")
                
                # If no code was executed, this is a text-only response
                if not custom_code_executed:
                    logging.info("📝 Extracting text-only response")
                    text_response = extract_agent_text_response(thread.id)
                    
                    return {
                        "status": "success",
                        "content": text_response,
                        "type": "text_response",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id
                    }
                else:
                    # Code was executed, return the analysis data
                    logging.info("✅ Completed with code execution")
                    return {
                        "status": "success",
                        "content": "Analysis completed",
                        "type": "code_execution_complete",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "analysis_data": analysis_data
                    }
            
            # ===== CASE 2: REQUIRES_ACTION (Tool call needed) =====
            elif run.status == "requires_action":
                logging.info("🛠️ Run requires action - processing tool calls")
                
                if run.required_action and run.required_action.submit_tool_outputs:
                    tool_calls = run.required_action.submit_tool_outputs.tool_calls
                    logging.info(f"🔧 Processing {len(tool_calls)} tool call(s)")
                    
                    tool_outputs = []
                    
                    for tool_call in tool_calls:
                        if tool_call.function.name == "execute_custom_code":
                            try:
                                # Parse arguments
                                raw_arguments = tool_call.function.arguments
                                
                                if not raw_arguments or not raw_arguments.strip():
                                    logging.warning("⚠️ Empty arguments, using fallback")
                                    function_args = {
                                        "python_code": "result = 'No code provided'",
                                        "user_request": user_query
                                    }
                                else:
                                    function_args = json.loads(raw_arguments)
                                
                                logging.info("🚀 Executing custom code...")
                                analysis_result = execute_custom_code(function_args)
                                custom_code_executed = True
                                analysis_data = analysis_result
                                
                                # Check if result is a map
                                if analysis_result.get("status") == "success":
                                    result_value = analysis_result.get("result")
                                    
                                    # Handle map results
                                    if isinstance(result_value, dict) and ("static_url" in result_value or "overlay_url" in result_value):
                                        logging.info("🗺️ Map result detected")
                                        
                                        # Normalize the result
                                        enriched = normalize_map_result_dict(result_value, user_query)
                                        enriched["temperature_data"] = build_temperature_data(enriched.get("geojson", {}))
                                        
                                        # Decide between tiles and overlay
                                        use_tiles = should_use_tiles(user_query, enriched)
                                        
                                        if use_tiles:
                                            # Generate tile configuration
                                            tile_config = create_tile_config(enriched, user_query)
                                            
                                            # Submit tool outputs
                                            tool_outputs.append({
                                                "tool_call_id": tool_call.id,
                                                "output": json.dumps({"status": "success", "completed": True})
                                            })
                                            
                                            project_client.agents.runs.submit_tool_outputs(
                                                thread_id=thread.id,
                                                run_id=run.id,
                                                tool_outputs=tool_outputs
                                            )
                                            
                                            return {
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
                                                "analysis_data": analysis_result
                                            }
                                        else:
                                            # Use PNG overlay
                                            return {
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
                                                "analysis_data": analysis_result
                                            }
                                    else:
                                        # Text result
                                        logging.info("📝 Text result detected")
                                        tool_outputs.append({
                                            "tool_call_id": tool_call.id,
                                            "output": json.dumps({"status": "success", "result": str(result_value)})
                                        })
                                else:
                                    # Execution failed
                                    error_msg = analysis_result.get("error", "Unknown error")
                                    logging.error(f"❌ Code execution failed: {error_msg}")
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
                return {
                    "status": "error",
                    "content": f"Agent run {run.status}",
                    "type": f"run_{run.status}",
                    "agent_id": text_agent_id,
                    "thread_id": thread.id
                }
            
            # ===== CASE 4: QUEUED/IN_PROGRESS =====
            elif run.status in ["queued", "in_progress"]:
                # Wait and continue
                time.sleep(0.5)
            
            # Refresh run status
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"❌ Error refreshing run: {e}")
                break
        
        # If we exit the loop without returning, something went wrong
        elapsed_time = time.time() - start_time
        logging.error(f"❌ Exited loop after {iteration} iterations, status: {run.status}")
        
        return {
            "status": "timeout_failure",
            "content": f"Agent failed after {iteration} iterations ({elapsed_time:.1f}s). Status: {run.status}",
            "type": "timeout",
            "agent_id": text_agent_id,
            "thread_id": thread.id,
            "debug": {
                "iterations": iteration,
                "final_status": run.status,
                "elapsed_time": elapsed_time
            }
        }
        
    except Exception as e:
        logging.error(f"❌ Chat request error: {e}", exc_info=True)
        return {
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__
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

# NEW: Build temperature_data array from geojson features
def build_temperature_data(geojson: dict, target_max_points: int = 2500) -> list:
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
    # Ensure extremes included
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
    try:
        return [
            float((bounds.get("east")+bounds.get("west"))/2),  # ✅ FIXED: Added missing closing parenthesis
            float((bounds.get("north")+bounds.get("south"))/2)  # ✅ FIXED: Added missing closing parenthesis
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
    return True  # Always return True

# Add compatibility wrapper at the end:
def chat_with_agent(user_query: str, thread_id: str = None):
    """Main entry point for chatting with the agent"""
    return handle_chat_request(user_query, thread_id)