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
from .memory_manager import memory_manager

# Load agent info (keep existing code)
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
    #handling different versions of the Azure AI SDK
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
    Create tile configuration - NO TIME DEFAULTS
    """
    import re
    import mercantile
    
    # Extract date and variable - NO DEFAULTS
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
        date_str = f"{year}-{month:02d}"  # SPI is monthly
    else:
        # For daily variables, require day specification
        day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', user_query)
        if not day_match or not (1 <= int(day_match.group(1)) <= 31):
            return {"error": "No valid day specified in query"}
        day = int(day_match.group(1))
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

def handle_chat_request(data):
    """Handle chat requests compatible with intelligent agent"""
    try:
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        logging.info(f"Processing chat request: {user_query}")
        
        # ✅ FIXED: Get user_id from request data
        user_id = data.get("user_id", f"anonymous_{hash(user_query) % 10000}")
        logging.info(f"👤 User ID: {user_id}")

        # ✅ FIXED: Retrieve memory context BEFORE sending to agent
        recent_memories = memory_manager.recent_context(user_id, limit=3)
        
        # ✅ FIXED: Search for relevant context based on query
        relevant_memories = memory_manager.search(user_query, user_id, limit=3)

        # Build enhanced query with memory context
        memory_context = ""
        if recent_memories or relevant_memories:
            memory_context = "\n\n🧠 Recent context from your previous queries:\n"
            
            # Add recent memories
            if recent_memories:
                memory_context += "Recent conversations:\n"
                for mem in recent_memories[:2]:
                    memory_context += f"- {mem}\n"
            
            # Add relevant memories
            if relevant_memories:
                memory_context += "\nRelevant previous analyses:\n"
                for mem in relevant_memories[:2]:
                    mem_text = mem.get("memory", "")
                    if mem_text:
                        memory_context += f"- {mem_text}\n"

        enhanced_query = user_query + memory_context
        logging.info(f"📝 Enhanced query with memory: {len(memory_context)} chars of context")

        # Create a thread for the conversation
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")
        
        # Send the enhanced query with memory context
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=enhanced_query
        )
        logging.info(f"Created message: {message.id}")
        
        # Start the agent run
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        logging.info(f"Started run: {run.id}")
        
        # Enhanced timeout and iteration handling
        max_iterations = 15
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        
        start_time = time.time()
        max_total_time = 60  # 60 seconds timeout
        
        while iteration < max_iterations:
            iteration += 1
            elapsed_time = time.time() - start_time
            
            logging.info(f"🔄 Run status: {run.status} (iteration {iteration}/{max_iterations}, elapsed: {elapsed_time:.1f}s)")
            
            if elapsed_time > max_total_time:
                logging.warning(f"⏰ TIMEOUT: Exceeded {max_total_time}s")
                break
            
            # ===== CASE 1: COMPLETED (Agent finished - could be text OR code execution) =====
            if run.status == "completed":
                logging.info("✅ Run completed")
                
                if not custom_code_executed:
                    # This is a text-only response (greeting, capability question, etc.)
                    text_response = extract_agent_text_response(thread.id)
                    
                    # ✅ STORE TEXT RESPONSE IN MEMORY
                    memory_manager.add(
                        f"Query: {user_query}\nResponse: {text_response}",
                        user_id,
                        {"type": "conversation", "query": user_query}
                    )
                    logging.info(f"💾 Stored conversation in memory for user {user_id}")
                    
                    response = {
                        "status": "success",
                        "content": text_response,
                        "type": "text_response",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "user_id": user_id
                    }
                    
                    return make_json_serializable(response)
                else:
                    # Code was executed
                    response = {
                        "status": "success",
                        "content": "Analysis completed",
                        "type": "code_execution_complete",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "analysis_data": analysis_data,
                        "user_id": user_id
                    }
                    
                    return make_json_serializable(response)
            
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
                                raw_arguments = tool_call.function.arguments
                                
                                if not raw_arguments or not raw_arguments.strip():
                                    logging.warning("⚠️ Empty arguments, using fallback")
                                    function_args = {
                                        "python_code": "result = 'Hello! I can help you with weather data analysis.'",
                                        "user_request": user_query
                                    }
                                else:
                                    function_args = json.loads(raw_arguments)
                                
                                # ✅ PASS USER_ID to code execution
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
                                        
                                        # ✅ STORE ANALYSIS IN MEMORY BEFORE PROCESSING
                                        extracted_info = extract_analysis_info(user_query, result_value)
                                        
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
                                        
                                        enriched = normalize_map_result_dict(result_value, user_query)
                                        enriched["temperature_data"] = build_temperature_data(enriched.get("geojson", {}))
                                        
                                        use_tiles = should_use_tiles(user_query, enriched)
                                        
                                        if use_tiles:
                                            tile_config = create_tile_config(enriched, user_query)
                                            
                                            tool_outputs.append({
                                                "tool_call_id": tool_call.id,
                                                "output": json.dumps({"status": "success", "completed": True})
                                            })
                                            
                                            project_client.agents.runs.submit_tool_outputs(
                                                thread_id=thread.id,
                                                run_id=run.id,
                                                tool_outputs=tool_outputs
                                            )
                                            
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
                                                "user_id": user_id
                                            }
                                            
                                            return make_json_serializable(response)
                                        
                                        else:
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
                                                "user_id": user_id
                                            }
                                            
                                            return make_json_serializable(response)
                                    else:
                                        # Text result
                                        # ✅ STORE NON-MAP RESULTS IN MEMORY TOO
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
                response = {
                    "status": "error",
                    "content": f"Agent run {run.status}",
                    "type": f"run_{run.status}",
                    "agent_id": text_agent_id,
                    "thread_id": thread.id,
                    "user_id": user_id
                }
                
                return make_json_serializable(response)
            
            # ===== CASE 4: QUEUED/IN_PROGRESS =====
            elif run.status in ["queued", "in_progress"]:
                time.sleep(0.5)
            
            # Refresh run status
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"❌ Error refreshing run: {e}")
                break
        
        # Final timeout response
        elapsed_time = time.time() - start_time
        logging.error(f"❌ Agent completion without execution:")
        logging.error(f"   Final status: {run.status}")
        logging.error(f"   Iterations: {iteration}/{max_iterations}")
        logging.error(f"   Elapsed time: {elapsed_time:.1f}s")
        
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
            }
        }
        
        return make_json_serializable(response)
        
    except Exception as e:
        logging.error(f"❌ Chat request error: {e}", exc_info=True)
        response = {
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__,
            "user_id": data.get("user_id", "unknown")
        }
        
        return make_json_serializable(response)


# ✅ ADD THIS HELPER FUNCTION (place it before handle_chat_request or after it)
def extract_analysis_info(query: str, result: dict) -> dict:
    """Extract variable, region, and date from query and result"""
    import re
    
    query_lower = query.lower()
    
    # Extract variable
    variable = "Tair"  # default
    if any(word in query_lower for word in ['precipitation', 'rain', 'rainfall']):
        variable = "Rainf"
    elif any(word in query_lower for word in ['drought', 'spi']):
        variable = "SPI3"
    elif 'temperature' in query_lower or 'temp' in query_lower:
        variable = "Tair"
    
    # Extract region
    region = "unknown"
    regions = {
        'michigan': 'michigan',
        'florida': 'florida',
        'california': 'california',
        'maryland': 'maryland',
        'texas': 'texas',
        'alaska': 'alaska'
    }
    for key, value in regions.items():
        if key in query_lower:
            region = value
            break
    
    # Extract date
    year_match = re.search(r'(20\d{2})', query)
    year = int(year_match.group(1)) if year_match else 2023
    
    month_names = ['january','february','march','april','may','june','july','august','september','october','november','december']
    month_match = re.search(r'(' + '|'.join(month_names) + ')', query_lower)
    month = month_names.index(month_match.group(1)) + 1 if month_match else 6
    
    day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', query)
    day = int(day_match.group(1)) if day_match and variable != "SPI3" else 15
    
    if variable == "SPI3":
        date_str = f"{year}-{month:02d}"
    else:
        date_str = f"{year}-{month:02d}-{day:02d}"
    
    return {
        "variable": variable,
        "region": region,
        "date_str": date_str
    }

def make_json_serializable(obj):
    """Enhanced JSON serialization that handles all Python types including mappingproxy"""
    import types
    from datetime import datetime, date
    
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, types.MappingProxyType):
        # Convert mappingproxy to regular dict
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif hasattr(obj, '__dict__'):
        return make_json_serializable(obj.__dict__)
    elif hasattr(obj, '_asdict'):  # namedtuple
        return make_json_serializable(obj._asdict())
    else:
        try:
            return str(obj)
        except:
            return f"<non-serializable: {type(obj).__name__}>"

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