# agents/agent_chat.py - Fixed version with better timeout and error handling
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
from .dynamic_code_generator import execute_custom_code
<<<<<<< HEAD
import numpy as np
import builtins
from .memory_manager import memory_manager
=======
import time
import json  # Also needed for logging the timing breakdown
>>>>>>> origin/feature/debug

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
<<<<<<< HEAD
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
=======
    ULTRA-DIRECT: Immediate function execution with Azure Maps detection + Performance Timing
    """
    start_total = time.time()
    times = {}
    
    try:
        # Validation step
        t1 = time.time()
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        logging.info(f"Processing chat request: {user_query}")
        times['validation'] = time.time() - t1

        # Thread creation
        t2 = time.time()
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")
        times['thread_creation'] = time.time() - t2
        
        # Message preparation
        t3 = time.time()
        enhanced_query = f"""IMMEDIATE ACTION REQUIRED: {user_query}

You MUST call execute_custom_code function RIGHT NOW. No thinking, no explanations.

Example for ANY request:
{{
  "python_code": "import builtins\\nds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)\\ndata = ds['Tair'].sel(lat=builtins.slice(58, 72), lon=builtins.slice(-180, -120)).mean()\\ntemp_c = float(data.values) - 273.15\\nds.close()\\nresult = f'Alaska temperature: {{temp_c:.1f}}°C'",
  "user_request": "{user_query}"
}}

CALL execute_custom_code NOW!"""

        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user", 
            content=enhanced_query
        )
        logging.info(f"Created message: {message.id}")
        times['message_creation'] = time.time() - t3
        
        # Run creation
        t4 = time.time()
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        logging.info(f"Started run: {run.id}")
        times['run_creation'] = time.time() - t4
        
        # Analysis detection
        t5 = time.time()
        analysis_keywords = ['most significant', 'most extreme', 'hottest', 'coldest', 'warmest', 'wettest', 'driest', 'highest', 'lowest', 'top', 'worst', 'best', 'find', 'where are']
        is_analysis_query = any(phrase in user_query.lower() for phrase in analysis_keywords)
        times['analysis_detection'] = time.time() - t5
        
        if is_analysis_query:
            # Direct analysis timing
            t6 = time.time()
            logging.info(f"🔍 Detected analysis query - using direct analysis function")
            try:
                from .dynamic_code_generator import analyze_extreme_regions
                analysis_result = analyze_extreme_regions(user_query)
                times['direct_analysis'] = time.time() - t6
                times['total'] = time.time() - start_total
                
                logging.info(f"⏱️  ANALYSIS TIMING: {json.dumps(times, indent=2)}")
                
                if analysis_result.get("status") == "success":
                    result_value = analysis_result.get("result")
                    
                    # FIXED: Return the complete structured analysis response that frontend expects
                    return {
                        "status": "success",
                        "content": f"Analysis completed: Found {len(result_value.get('regions', []))} extreme regions",
                        "analysis_data": analysis_result,
                        "type": "analysis_complete",
                        # CRITICAL: Add these fields that frontend expects for analysis results
                        "regions": result_value.get("regions", []),
                        "geojson": result_value.get("geojson", {}),
                        "bounds": result_value.get("bounds", {}),
                        "map_config": result_value.get("map_config", {}),
                        "variable": result_value.get("variable"),
                        "analysis_type": result_value.get("analysis_type"),
                        # NEW: Add temperature_data for consistency with other responses
                        "temperature_data": build_temperature_data(result_value.get("geojson", {})),
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "timing_breakdown": times
                    }
                else:
                    return {
                        "status": "error",
                        "content": f"Analysis failed: {analysis_result.get('error', 'Unknown error')}",
                        "type": "analysis_error",
                        "timing_breakdown": times
                    }
                    
            except Exception as analysis_error:
                times['direct_analysis_failed'] = time.time() - t6
                logging.error(f"❌ Direct analysis failed: {analysis_error}")
                # Fall back to agent-based processing
                logging.info("🔄 Falling back to agent-based analysis")

        # Execution loop timing
        t7 = time.time()
        max_iterations = 15
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        final_response_content = None
        in_progress_count = 0
        
        start_time = time.time()
        max_total_time = 120  # Increased to 2 minutes
        max_in_progress_time = 8  # NEW: Max time to stay in "in_progress"
        last_status_change = start_time
>>>>>>> origin/feature/debug
        
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
    
    # Generate tile list
    tile_list = []
    for x in range(nw_tile.x, se_tile.x + 1):
        for y in range(nw_tile.y, se_tile.y + 1):
            tile_bounds = mercantile.bounds(mercantile.Tile(x, y, zoom))
            
<<<<<<< HEAD
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

=======
            logging.info(f"🔄 Run status: {run.status} (iteration {iteration}/{max_iterations}, elapsed: {elapsed_time:.1f}s)")
            
            # ENHANCED: Status-specific timeout handling
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
                            content="EXECUTE FUNCTION NOW! Call execute_custom_code immediately with any simple code."
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
            
            # Overall timeout
            if elapsed_time > max_total_time:
                logging.warning(f"⏰ TIMEOUT: Exceeded {max_total_time}s total time limit")
                break
            
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    logging.info(f"🔧 Function call requested: {func_name}")
                    
                    if func_name == "execute_custom_code":
                        if custom_code_executed:
                            logging.info("✅ Custom code already executed, skipping")
                            continue
                        
                        try:
                            # ENHANCED: Better argument parsing
                            raw_arguments = tool_call.function.arguments
                            logging.info(f"📝 Raw arguments length: {len(raw_arguments) if raw_arguments else 0}")
                            
                            if not raw_arguments or not raw_arguments.strip():
                                # ENHANCED: Better emergency fallback based on user query
                                logging.warning("⚠️ Using enhanced emergency fallback code")
                                
                                # Detect what the user wants
                                if any(word in user_query.lower() for word in ['map', 'show', 'visualiz', 'plot']):
                                    fallback_code = """import builtins
import time
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)
data = ds['Tair'].sel(lat=builtins.slice(58, 72), lon=builtins.slice(-180, -120)).isel(time=0)
temp_celsius = data - 273.15
import cartopy.crs as ccrs
import cartopy.feature as cfeature

fig = plt.figure(figsize=(12, 8))
fig.patch.set_facecolor('white')
ax = plt.axes(projection=ccrs.PlateCarree())

# Version-compatible background removal
try:
    ax.background_patch.set_visible(False)
except AttributeError:
    try:
        ax.outline_patch.set_visible(False)
    except AttributeError:
        pass

im = ax.pcolormesh(data.lon, data.lat, temp_celsius, cmap='coolwarm', 
                   shading='auto', transform=ccrs.PlateCarree())
ax.add_feature(cfeature.COASTLINE, linewidth=0.8, color='black', alpha=0.8)
ax.add_feature(cfeature.STATES, linewidth=0.4, color='gray', alpha=0.6)
gl = ax.gridlines(draw_labels=True, alpha=0.3, linestyle='--', linewidth=0.5)
gl.top_labels = False
gl.right_labels = False
cbar = plt.colorbar(im, ax=ax)
cbar.set_label('Temperature (°C)', fontsize=16)
ax.set_title('Alaska Temperature Map', fontsize=16)
filename = f'alaska_temp_{int(time.time())}.png'
url = save_plot_to_blob_simple(fig, filename, account_key)
plt.close(fig)
ds.close()
result = url"""
                                else:
                                    fallback_code = """import builtins
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)
data = ds['Tair'].sel(lat=builtins.slice(58, 72), lon=builtins.slice(-180, -120)).mean()
temp_c = float(data.values) - 273.15
ds.close()
result = f'The average temperature in Alaska is {temp_c:.1f}°C'"""
                                
                                function_args = {
                                    "python_code": fallback_code,
                                    "user_request": user_query
                                }
                            else:
                                try:
                                    function_args = json.loads(raw_arguments)
                                    logging.info("✅ Successfully parsed JSON arguments")
                                except json.JSONDecodeError as json_error:
                                    logging.warning(f"⚠️ JSON parsing failed: {json_error}")
                                    # Try to extract from potential markdown
                                    if 'python_code' in raw_arguments:
                                        # Use fallback
                                        function_args = {
                                            "python_code": """import builtins
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)
data = ds['Tair'].sel(lat=builtins.slice(58, 72), lon=builtins.slice(-180, -120)).mean()
temp_c = float(data.values) - 273.15
ds.close()
result = f'The temperature is {temp_c:.1f}°C'""",
                                            "user_request": user_query
                                        }
                                    else:
                                        raise ValueError("Could not parse function arguments")
                            
                            logging.info(f"🚀 EXECUTING CODE NOW...")
                            
                            # Execute the code
                            analysis_result = execute_custom_code(function_args)
                            analysis_data = analysis_result
                            custom_code_executed = True
                            
                            # IMMEDIATE: Handle success/failure
                            if analysis_result.get("status") == "success":
                                result_value = analysis_result.get("result", "No result")

                                # UPDATED: Full map dict (dual URLs)
                                if isinstance(result_value, dict) and ("overlay_url" in result_value or "static_url" in result_value):
                                    enriched = normalize_map_result_dict(result_value, user_query)
                                    enriched["temperature_data"] = build_temperature_data(enriched.get("geojson"))
                                    tool_outputs.append({
                                        "tool_call_id": tool_call.id,
                                        "output": json.dumps({"status": "success", "completed": True})
                                    })
                                    times['execution_loop'] = time.time() - t7
                                    times['total'] = time.time() - start_total
                                    
                                    # Log timing breakdown
                                    logging.info(f"⏱️  COMPLETE TIMING BREAKDOWN:")
                                    logging.info(f"   📋 Validation: {times.get('validation', 0):.3f}s")
                                    logging.info(f"   🧵 Thread creation: {times.get('thread_creation', 0):.3f}s")
                                    logging.info(f"   💬 Message creation: {times.get('message_creation', 0):.3f}s")
                                    logging.info(f"   🚀 Run creation: {times.get('run_creation', 0):.3f}s")
                                    logging.info(f"   🔍 Analysis detection: {times.get('analysis_detection', 0):.3f}s")
                                    logging.info(f"   ⚙️  Execution loop: {times.get('execution_loop', 0):.3f}s")
                                    logging.info(f"   🎯 TOTAL TIME: {times['total']:.3f}s")
                                    
                                    return {
                                        "status": "success",
                                        "content": enriched.get("static_url") or enriched["overlay_url"],
                                        "static_url": enriched.get("static_url"),
                                        "overlay_url": enriched["overlay_url"],
                                        "geojson": enriched["geojson"],
                                        "bounds": enriched["bounds"],
                                        "map_config": enriched["map_config"],
                                        "temperature_data": enriched["temperature_data"],
                                        "type": "visualization_with_overlay",
                                        "agent_id": text_agent_id,
                                        "thread_id": thread.id,
                                        "analysis_data": analysis_result,
                                        "timing_breakdown": times
                                    }

                                # Legacy single URL path
                                if isinstance(result_value, str) and result_value.startswith("http"):
                                    enriched = wrap_with_geo_overlay(result_value, user_query)
                                    enriched["temperature_data"] = build_temperature_data(enriched.get("geojson"))
                                    tool_outputs.append({
                                        "tool_call_id": tool_call.id,
                                        "output": json.dumps({"status": "success", "completed": True})
                                    })
                                    times['execution_loop'] = time.time() - t7
                                    times['total'] = time.time() - start_total
                                    
                                    # Log timing breakdown
                                    logging.info(f"⏱️  COMPLETE TIMING BREAKDOWN:")
                                    logging.info(f"   📋 Validation: {times.get('validation', 0):.3f}s")
                                    logging.info(f"   🧵 Thread creation: {times.get('thread_creation', 0):.3f}s")
                                    logging.info(f"   💬 Message creation: {times.get('message_creation', 0):.3f}s")
                                    logging.info(f"   🚀 Run creation: {times.get('run_creation', 0):.3f}s")
                                    logging.info(f"   🔍 Analysis detection: {times.get('analysis_detection', 0):.3f}s")
                                    logging.info(f"   ⚙️  Execution loop: {times.get('execution_loop', 0):.3f}s")
                                    logging.info(f"   🎯 TOTAL TIME: {times['total']:.3f}s")
                                    
                                    return {
                                        "status": "success",
                                        "content": enriched["static_url"],
                                        "static_url": enriched["static_url"],
                                        "overlay_url": enriched["overlay_url"],
                                        "geojson": enriched["geojson"],
                                        "bounds": enriched.get("bounds"),
                                        "map_config": enriched["map_config"],
                                        "temperature_data": enriched["temperature_data"],
                                        "type": "visualization_with_overlay",
                                        "agent_id": text_agent_id,
                                        "thread_id": thread.id,
                                        "analysis_data": analysis_result,
                                        "timing_breakdown": times
                                    }

                                # IMPROVED: Clean up the response format - remove icons and make it conversational
                                if isinstance(result_value, str):
                                    # If it's already a formatted string (like "Alaska temperature: -16.4°C"), use it directly
                                    if any(phrase in result_value.lower() for phrase in ['temperature', 'precipitation', 'humidity', 'pressure']):
                                        # Convert technical format to conversational format
                                        if 'temperature:' in result_value.lower():
                                            # Convert "Alaska temperature: -16.4°C" to "The average temperature in Alaska is -16.4°C"
                                            parts = result_value.split(':')
                                            if len(parts) == 2:
                                                location_var = parts[0].strip()
                                                value = parts[1].strip()
                                                if 'alaska' in location_var.lower():
                                                    final_response_content = f"The average temperature in Alaska is {value}"
                                                else:
                                                    final_response_content = f"The average {location_var.lower()} is {value}"
                                            else:
                                                final_response_content = result_value
                                        elif 'precipitation' in result_value.lower():
                                            # Handle precipitation results
                                            final_response_content = result_value
                                        else:
                                            final_response_content = result_value
                                    elif result_value.startswith('http'):
                                        # It's a URL (map/visualization)
                                        final_response_content = result_value
                                    else:
                                        # Other string results
                                        final_response_content = result_value
                                else:
                                    # For non-string results (dict, etc.), keep as is
                                    final_response_content = str(result_value)
                                
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({"status": "success", "completed": True})
                                })
                                
                                # Calculate final timings
                                times['execution_loop'] = time.time() - t7
                                times['total'] = time.time() - start_total
                                
                                # Log the complete timing breakdown
                                logging.info(f"⏱️  COMPLETE TIMING BREAKDOWN:")
                                logging.info(f"   📋 Validation: {times.get('validation', 0):.3f}s")
                                logging.info(f"   🧵 Thread creation: {times.get('thread_creation', 0):.3f}s")
                                logging.info(f"   💬 Message creation: {times.get('message_creation', 0):.3f}s")
                                logging.info(f"   🚀 Run creation: {times.get('run_creation', 0):.3f}s")
                                logging.info(f"   🔍 Analysis detection: {times.get('analysis_detection', 0):.3f}s")
                                logging.info(f"   ⚙️  Execution loop: {times.get('execution_loop', 0):.3f}s")
                                logging.info(f"   🎯 TOTAL TIME: {times['total']:.3f}s")
                                
                                # IMMEDIATE RETURN
                                return {
                                    "status": "success",
                                    "content": final_response_content,
                                    "type": "immediate_success_return",
                                    "agent_id": text_agent_id,
                                    "thread_id": thread.id,
                                    "debug": {
                                        "iterations": iteration,
                                        "elapsed_time": elapsed_time,
                                        "custom_code_executed": True
                                    },
                                    "analysis_data": analysis_result,
                                    "timing_breakdown": times
                                }
                                
                            else:
                                error_msg = analysis_result.get("error", "Unknown error")
                                final_response_content = f"❌ Code execution failed: {error_msg}"
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({"status": "error", "error": error_msg[:50]})
                                })
                            
                        except Exception as e:
                            logging.error(f"💥 Execution error: {e}")
                            final_response_content = f"❌ Execution failed: {str(e)}"
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": json.dumps({"status": "error", "error": str(e)[:50]})
                            })
                    
                    else:
                        # Skip other functions
                        logging.info(f"⏭️ Skipping function: {func_name}")

                # Submit tool outputs
                if tool_outputs:
                    try:
                        logging.info("📤 Submitting tool outputs...")
                        run = project_client.agents.runs.submit_tool_outputs(
                            thread_id=thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                        logging.info("✅ Tool outputs submitted")
                    except Exception as e:
                        logging.error(f"❌ Tool output submission failed: {e}")
                        # Return result anyway if we have it
                        if custom_code_executed and final_response_content:
                            times['execution_loop'] = time.time() - t7
                            times['total'] = time.time() - start_total
                            return {
                                "status": "success",
                                "content": final_response_content,
                                "type": "submission_failed_but_success",
                                "agent_id": text_agent_id,
                                "thread_id": thread.id,
                                "analysis_data": analysis_data,
                                "timing_breakdown": times
                            }
                
                # Return if code executed
                if custom_code_executed and final_response_content:
                    times['execution_loop'] = time.time() - t7
                    times['total'] = time.time() - start_total
                    
                    # Log timing breakdown
                    logging.info(f"⏱️  COMPLETE TIMING BREAKDOWN:")
                    logging.info(f"   📋 Validation: {times.get('validation', 0):.3f}s")
                    logging.info(f"   🧵 Thread creation: {times.get('thread_creation', 0):.3f}s")
                    logging.info(f"   💬 Message creation: {times.get('message_creation', 0):.3f}s")
                    logging.info(f"   🚀 Run creation: {times.get('run_creation', 0):.3f}s")
                    logging.info(f"   🔍 Analysis detection: {times.get('analysis_detection', 0):.3f}s")
                    logging.info(f"   ⚙️  Execution loop: {times.get('execution_loop', 0):.3f}s")
                    logging.info(f"   🎯 TOTAL TIME: {times['total']:.3f}s")
                    
                    return {
                        "status": "success",
                        "content": final_response_content,
                        "type": "post_submission_success",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "debug": {
                            "iterations": iteration,
                            "elapsed_time": elapsed_time,
                            "custom_code_executed": True
                        },
                        "analysis_data": analysis_data,
                        "timing_breakdown": times
                    }
            
            # Enhanced: Variable wait time based on status
            if run.status == "in_progress":
                time.sleep(0.1)  # Longer wait when thinking
            else:
                time.sleep(0.05)  # Shorter wait for other statuses
                
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"❌ Get run error: {e}")
                break
        
        # Enhanced final status logging
        times['execution_loop'] = time.time() - t7
        times['total'] = time.time() - start_total
        
        final_status = run.status if 'run' in locals() else "unknown"
        logging.error(f"❌ Agent completion without execution:")
        logging.error(f"   Final status: {final_status}")
        logging.error(f"   Iterations: {iteration}/{max_iterations}")
        logging.error(f"   Elapsed time: {elapsed_time:.1f}s")
        logging.error(f"   Custom code executed: {custom_code_executed}")
        
        # Log timing breakdown even on failure
        logging.info(f"⏱️  ERROR TIMING: {json.dumps(times, indent=2)}")
        
        # Final fallback
        if custom_code_executed and final_response_content:
            return {
                "status": "success",
                "content": final_response_content,
                "type": "final_fallback_success",
                "agent_id": text_agent_id,
                "thread_id": thread.id,
                "analysis_data": analysis_data,
                "timing_breakdown": times
            }
        
        # Timeout response with more helpful message
        elapsed_time = time.time() - start_time
        return {
            "status": "timeout_failure", 
            "content": f"Agent failed to execute function after {max_iterations} iterations ({elapsed_time:.1f}s). The agent appears to be stuck in '{final_status}' status. This may require agent recreation.",
            "type": "iteration_limit_exceeded",
            "agent_id": text_agent_id,
            "thread_id": thread.id,
            "debug": {
                "iterations": iteration,
                "max_iterations": max_iterations,
                "elapsed_time": elapsed_time,
                "final_status": final_status,
                "custom_code_executed": custom_code_executed,
                "suggestion": "Recreate the agent: python agents/agent_creation.py"
            },
            "timing_breakdown": times
        }
        
    except Exception as e:
        times['total'] = time.time() - start_total
        logging.error(f"❌ Request error: {e}", exc_info=True)
        logging.info(f"⏱️  ERROR TIMING: {json.dumps(times, indent=2)}")
        return {
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__,
            "timing_breakdown": times
        }
>>>>>>> origin/feature/debug
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
        memory_context_str = ""  # ← Changed name
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

        enhanced_query = user_query + memory_context_str  # ← Also change here
            
        
     

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
                                        extracted_info = extract_analysis_info(user_query, result_value, memory_context_str)
                                        
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
                                            tile_config = create_tile_config(enriched, user_query, extracted_info)
                                            
                                            # ✅ Check if tile config failed
                                            if "error" in tile_config:
                                                logging.warning(f"⚠️ Tile generation failed: {tile_config['error']}")
                                                logging.info("📍 Falling back to static-only response")
                                                
                                                # Return static-only response
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
                                                    "tile_error": tile_config.get('error')
                                                }
                                                
                                                return make_json_serializable(response)
                                            
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
def extract_analysis_info(query: str, result: dict, memory_context: str = "") -> dict:
    """
    Extract variable, region, and date from query, result, and memory context
    
    Args:
        query: Current user query
        result: Result dict from code execution
        memory_context: Recent memory context string
    """
    import re
    
    query_lower = query.lower()
    
    # ✅ STEP 1: Extract variable (check memory FIRST for "same" queries)
    variable = None
    
    if any(word in query_lower for word in ['same', 'similar', 'that', 'this']):
        # Look for variable in memory context
        if 'SPI3' in memory_context or 'drought' in memory_context.lower():
            variable = "SPI3"
            logging.info("📝 Extracted variable from memory: SPI3 (drought)")
        elif 'Rainf' in memory_context or 'precipitation' in memory_context.lower():
            variable = "Rainf"
            logging.info("📝 Extracted variable from memory: Rainf (precipitation)")
        elif 'Tair' in memory_context or 'temperature' in memory_context.lower():
            variable = "Tair"
            logging.info("📝 Extracted variable from memory: Tair (temperature)")
    
    # If not found in memory, extract from current query
    if not variable:
        if any(word in query_lower for word in ['drought', 'spi']):
            variable = "SPI3"
        elif any(word in query_lower for word in ['precipitation', 'rain', 'rainfall']):
            variable = "Rainf"
        elif any(word in query_lower for word in ['temperature', 'temp']):
            variable = "Tair"
        else:
            variable = "Tair"  # Default
    
    # ✅ STEP 2: Extract region
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
    
    # ✅ STEP 3: Extract date (check memory for "same" queries)
    year = None
    month = None
    day = None
    
    if any(word in query_lower for word in ['same', 'similar', 'that', 'this']):
        # Extract date from memory (format: "2023-06-15" or "2023-06")
        memory_date_match = re.search(r'on (\d{4}-\d{2}(?:-\d{2})?)', memory_context)
        if memory_date_match:
            date_str = memory_date_match.group(1)
            date_parts = date_str.split('-')
            year = int(date_parts[0])
            month = int(date_parts[1])
            day = int(date_parts[2]) if len(date_parts) > 2 else None
            logging.info(f"📅 Extracted date from memory: {date_str}")
    
    # If not found in memory, extract from query
    if not year:
        year_match = re.search(r'(20\d{2})', query)
        year = int(year_match.group(1)) if year_match else 2023
    
    if not month:
        month_names = ['january','february','march','april','may','june','july','august','september','october','november','december']
        month_match = re.search(r'(' + '|'.join(month_names) + ')', query_lower)
        month = month_names.index(month_match.group(1)) + 1 if month_match else 6
    
    if day is None and variable != "SPI3":
        day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', query)
        day = int(day_match.group(1)) if day_match else 15
    
    # Build date string
    if variable == "SPI3":
        date_str = f"{year}-{month:02d}"
    else:
        date_str = f"{year}-{month:02d}-{day:02d}"
    
    logging.info(f"📊 Extracted: variable={variable}, region={region}, date={date_str}")
    
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