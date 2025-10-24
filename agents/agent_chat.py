# agents/agent_chat.py - Complete version with validation and proper response handling
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
from .dynamic_code_generator import execute_custom_code
from .query_validator import query_validator
import numpy as np
import builtins

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

def determine_optimal_zoom_level(bounds: dict) -> int:
    """
    Area-based zoom selection for optimal tile count
    
    Strategy: Linear scaling with area
    - Target: 2.5 tiles per 100 square degrees
    - Min: 6 tiles (small regions)
    - Max: 300 tiles (continental scale)
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
    
    return best_zoom

def create_tile_config(map_data: dict, user_query: str) -> dict:
    """
    Create tile configuration with REGION-SPECIFIC global scale and DYNAMIC zoom
    Uses area-based scaling - larger regions get MORE tiles at appropriate zoom
    """
    import re
    import mercantile
    
    # Extract date and variable
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
                region_vmin, region_vmax = 0, 30
        
        ds.close()
        logging.info(f"✅ Region color scale: {region_vmin:.2f} to {region_vmax:.2f}")
        
    except Exception as e:
        logging.error(f"❌ Failed to calculate region scale: {e}")
        if variable == 'SPI3':
            region_vmin, region_vmax = -2.5, 2.5
        else:
            region_vmin, region_vmax = 0, 30
    
    # Determine optimal zoom level
    zoom = determine_optimal_zoom_level(bounds)
    
    # Calculate tile grid
    nw_tile = mercantile.tile(west, north, zoom)
    se_tile = mercantile.tile(east, south, zoom)
    
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
    
    logging.info(f"✅ Generated {len(tile_list)} tiles: X={nw_tile.x}-{se_tile.x}, Y={nw_tile.y}-{se_tile.y}")
    
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

def handle_chat_request(data):
    """
    Main chat handler with validation and proper response handling
    """
    try:
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        thread_id_from_request = data.get("thread_id")
        
        logging.info(f"📝 Processing: {user_query}")
        logging.info(f"🧵 Thread ID from request: {thread_id_from_request}")

        # ===== VALIDATION =====
        validation = query_validator.validate_query(user_query)
        
        logging.info(f"🔍 Validation: is_data={validation['is_data_query']}, is_analysis={validation.get('is_analysis_query', False)}, valid={validation['is_valid']}")
        
        if validation['is_data_query'] and not validation['is_valid']:
            # Missing analysis method or area size - ask user
            if not thread_id_from_request:
                temp_thread = project_client.agents.threads.create()
                thread_id_from_request = temp_thread.id
                logging.info(f"✨ Created thread for validation: {thread_id_from_request}")
            
            return {
                "status": "success",
                "content": validation['message'],
                "type": "validation_error",
                "validation": validation,
                "thread_id": thread_id_from_request
            }

        # ===== THREAD MANAGEMENT =====
        thread = None
        if thread_id_from_request:
            try:
                thread = project_client.agents.threads.get_thread(thread_id=thread_id_from_request)
                logging.info(f"♻️ REUSING THREAD: {thread_id_from_request}")
            except Exception as e:
                logging.warning(f"⚠️ Could not reuse thread: {e}")
                thread = project_client.agents.threads.create()
                logging.info(f"✨ Created new thread after failure: {thread.id}")
        else:
            thread = project_client.agents.threads.create()
            logging.info(f"✨ Created NEW thread: {thread.id}")
        
        # ===== CONDITIONAL PROMPTING =====
        if validation['is_data_query']:
            # For data queries: Use directive prompt
            logging.info("📊 DATA QUERY - Using directive prompt")
            enhanced_query = f"""IMMEDIATE ACTION REQUIRED: {user_query}

🚨 CRITICAL: For ALL GeoJSON features, ALWAYS use "value" property:
- WRONG: {{"properties": {{"spi": -1.5}}}}
- RIGHT: {{"properties": {{"value": -1.5, "variable": "SPI3"}}}}

For SPI data specifically:
```python
# When creating GeoJSON for SPI, always use "value":
feature = {{
    "type": "Feature", 
    "geometry": {{"type": "Point", "coordinates": [lon, lat]}},
    "properties": {{
        "value": spi_value,  # ✅ Use "value", never "spi"
        "variable": "SPI3",
        "unit": "SPI"
    }}
}}
```

CALL execute_custom_code NOW!"""
        else:
            # For general conversation: Natural prompt
            logging.info("💬 GENERAL QUERY - Using natural prompt")
            enhanced_query = user_query

        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user", 
            content=enhanced_query
        )
        logging.info(f"📤 Created message: {message.id}")
        
        # Start the agent run
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        logging.info(f"▶️ Started run: {run.id}")
        
        # Detect analysis queries
        analysis_keywords = ['most significant', 'most extreme', 'hottest', 'coldest', 'warmest', 'wettest', 'driest', 'highest', 'lowest', 'top', 'worst', 'best', 'find', 'where are']
        is_analysis_query = any(phrase in user_query.lower() for phrase in analysis_keywords)
        
        if is_analysis_query:
            logging.info(f"🔍 Detected analysis query - using direct analysis function")
            try:
                from .dynamic_code_generator import analyze_extreme_regions
                analysis_result = analyze_extreme_regions(user_query)
                
                if analysis_result.get("status") == "success":
                    result_value = analysis_result.get("result")
                    
                    return {
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
                        "thread_id": thread.id
                    }
                    
            except Exception as analysis_error:
                logging.error(f"❌ Direct analysis failed: {analysis_error}")

        # Execution loop
        max_iterations = 15
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        final_response_content = None
        
        start_time = time.time()
        max_total_time = 120
        max_in_progress_time = 15
        last_status_change = start_time
        
        while run.status in ["queued", "in_progress", "requires_action"] and iteration < max_iterations:
            iteration += 1
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            logging.info(f"🔄 Run status: {run.status} (iteration {iteration}/{max_iterations}, elapsed: {elapsed_time:.1f}s)")
            
            if run.status == "in_progress":
                time_in_progress = current_time - last_status_change
                
                if time_in_progress > max_in_progress_time:
                    logging.warning(f"⚠️ Stuck in 'in_progress' for {time_in_progress:.1f}s")
                    try:
                        project_client.agents.runs.cancel(thread_id=thread.id, run_id=run.id)
                        time.sleep(1)
                        
                        direct_message = project_client.agents.messages.create(
                            thread_id=thread.id,
                            role="user",
                            content="EXECUTE FUNCTION NOW! Call execute_custom_code immediately."
                        )
                        
                        run = project_client.agents.runs.create(
                            thread_id=thread.id,
                            agent_id=text_agent_id
                        )
                        
                        last_status_change = time.time()
                        logging.info("🔄 Restarted run")
                        
                    except Exception as restart_error:
                        logging.error(f"❌ Failed to restart run: {restart_error}")
                        break
            else:
                if run.status != getattr(handle_chat_request, '_last_status', None):
                    last_status_change = current_time
                    handle_chat_request._last_status = run.status
            
            if elapsed_time > max_total_time:
                logging.warning(f"⏰ TIMEOUT: Exceeded {max_total_time}s")
                break
            
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    logging.info(f"🔧 Function call: {func_name}")
                    
                    if func_name == "execute_custom_code":
                        if custom_code_executed:
                            continue
                        
                        try:
                            raw_arguments = tool_call.function.arguments
                            
                            if not raw_arguments or not raw_arguments.strip():
                                logging.warning("⚠️ Using fallback code")
                                fallback_code = """import builtins
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)
data = ds['Tair'].sel(lat=builtins.slice(38, 40), lon=builtins.slice(-80, -75)).mean()
temp_c = float(data.values) - 273.15
ds.close()
result = f'Temperature: {temp_c:.1f}°C'"""
                                
                                function_args = {
                                    "python_code": fallback_code,
                                    "user_request": user_query
                                }
                            else:
                                function_args = json.loads(raw_arguments)
                            
                            logging.info(f"🚀 Executing code...")
                            analysis_result = execute_custom_code(function_args)
                            analysis_data = analysis_result
                            custom_code_executed = True
                            
                            if analysis_result.get("status") == "success":
                                result_value = analysis_result.get("result", "No result")

                                # Handle map results
                                if isinstance(result_value, dict) and ("overlay_url" in result_value or "static_url" in result_value):
                                    enriched = normalize_map_result_dict(result_value, user_query)
                                    enriched["temperature_data"] = build_temperature_data(enriched.get("geojson"))
                                    
                                    use_tiles = should_use_tiles(user_query, enriched)
                                    
                                    if use_tiles:
                                        tile_config = create_tile_config(enriched, user_query)
                                        tool_outputs.append({
                                            "tool_call_id": tool_call.id,
                                            "output": json.dumps({"status": "success", "completed": True})
                                        })
                                        return {
                                            "status": "success",
                                            "content": enriched.get("static_url") or "Map generated",
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
                                        tool_outputs.append({
                                            "tool_call_id": tool_call.id,
                                            "output": json.dumps({"status": "success", "completed": True})
                                        })
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
                                            "analysis_data": analysis_result
                                        }

                                # Handle text results
                                if isinstance(result_value, str):
                                    final_response_content = result_value
                                else:
                                    final_response_content = str(result_value)
                                
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({"status": "success", "completed": True})
                                })
                                
                                return {
                                    "status": "success",
                                    "content": final_response_content,
                                    "type": "text_result",
                                    "agent_id": text_agent_id,
                                    "thread_id": thread.id,
                                    "analysis_data": analysis_result
                                }
                                
                            else:
                                error_msg = analysis_result.get("error", "Unknown error")
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({"status": "error", "error": error_msg[:50]})
                                })
                            
                        except Exception as e:
                            logging.error(f"💥 Execution error: {e}")
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": json.dumps({"status": "error", "error": str(e)[:50]})
                            })

                # Submit tool outputs
                if tool_outputs:
                    try:
                        run = project_client.agents.runs.submit_tool_outputs(
                            thread_id=thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                    except Exception as e:
                        logging.error(f"❌ Tool output submission failed: {e}")
            
            time.sleep(0.5 if run.status == "in_progress" else 0.2)
                
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"❌ Get run error: {e}")
                break
        
        
        # ===== HANDLE COMPLETED STATUS (for text responses) =====
        if run.status == "completed":
            logging.info("✅ Run completed - fetching agent response")
            
            try:
                # List messages in the thread (returns ItemPaged iterator)
                messages = project_client.agents.messages.list(thread_id=thread.id)
                
                # Convert to list to make it easier to work with
                messages_list = list(messages)
                
                # Find the most recent assistant message
                for message in messages_list:
                    if message.role == "assistant":
                        # Extract the text content
                        if message.content and len(message.content) > 0:
                            content_block = message.content[0]
                            
                            # Handle different content types
                            if hasattr(content_block, 'text'):
                                text_content = content_block.text.value
                            elif hasattr(content_block, 'value'):
                                text_content = content_block.value
                            else:
                                text_content = str(content_block)
                            
                            logging.info(f"📨 Agent response: {text_content[:150]}...")
                            
                            return {
                                "status": "success",
                                "content": text_content,
                                "type": "text_response",
                                "agent_id": text_agent_id,
                                "thread_id": thread.id
                            }
                
                # No assistant message found - return friendly fallback
                logging.warning("⚠️ No assistant message found in completed run")
                return {
                    "status": "success",
                    "content": "Hello! I'm your hydrology and drought monitoring assistant. How can I help you today?",
                    "type": "fallback_response",
                    "thread_id": thread.id
                }
                
            except Exception as e:
                logging.error(f"❌ Error extracting response: {e}", exc_info=True)
                return {
                    "status": "error",
                    "content": "I encountered an issue. Please try again.",
                    "thread_id": thread.id
                }
        
        # Handle other statuses
        final_status = run.status if 'run' in locals() else "unknown"
        logging.error(f"❌ Agent ended with status: {final_status}")
        
        elapsed_time = time.time() - start_time
        return {
            "status": "timeout_failure", 
            "content": f"Agent failed to execute after {max_iterations} iterations ({elapsed_time:.1f}s). Status: '{final_status}'",
            "type": "iteration_limit_exceeded",
            "agent_id": text_agent_id,
            "thread_id": thread.id,
            "debug": {
                "iterations": iteration,
                "max_iterations": max_iterations,
                "elapsed_time": elapsed_time,
                "final_status": final_status
            }
        }
        
    except Exception as e:
        logging.error(f"❌ Request error: {e}", exc_info=True)
        return {
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__
        }

def wrap_with_geo_overlay(static_url: str, original_query: str) -> dict:
    """Wrap static URL with geo overlay structure"""
    geojson = {"type": "FeatureCollection", "features": []}
    map_config = {
        "style": "satellite",
        "overlay_mode": True,
        "center": [-98.0, 39.0],
        "zoom": 5
    }
    return {
        "static_url": static_url,
        "overlay_url": None,
        "geojson": geojson,
        "bounds": None,
        "map_config": map_config,
        "original_query": original_query
    }

def normalize_map_result_dict(raw: dict, original_query: str) -> dict:
    """Normalize map result dictionary"""
    static_url = raw.get("static_url")
    overlay_url = raw.get("overlay_url") or raw.get("transparent_url")
    
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
    """Build temperature data array from geojson features"""
    results = []
    if not geojson or geojson.get("type") != "FeatureCollection":
        return results
    
    features = geojson.get("features", [])
    total = len(features)
    if total == 0:
        return results
    
    stride = max(1, int(total / target_max_points)) if total > target_max_points else 1
    
    for idx, f in enumerate(features):
        if idx % stride != 0:
            continue
        
        geom = f.get("geometry", {})
        if geom.get("type") != "Point":
            continue
        
        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        
        lon, lat = float(coords[0]), float(coords[1])
        props = f.get("properties", {}) or {}
        val = props.get("value") or props.get("spi") or props.get("temperature")
        
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
    
    return results

def bounds_center(bounds: dict):
    """Calculate center of bounds"""
    try:
        return [
            float((bounds.get("east") + bounds.get("west")) / 2),
            float((bounds.get("north") + bounds.get("south")) / 2)
        ]
    except Exception:
        return [-98.0, 39.0]

def should_use_tiles(user_query: str, map_data: dict) -> bool:
    """Determine if tiles should be used"""
    bounds = map_data.get("bounds", {})
    if not bounds:
        return False
    
    logging.info("✅ Using tiles for map query")
    return True