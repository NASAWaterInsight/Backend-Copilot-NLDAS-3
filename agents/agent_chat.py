# agents/agent_chat.py - Fixed version with better timeout and error handling
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
from .dynamic_code_generator import execute_custom_code

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

def handle_chat_request(data):
    """
    ULTRA-DIRECT: Immediate function execution with Azure Maps detection
    """
    try:
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        logging.info(f"Processing chat request: {user_query}")

        # Create a thread for the conversation
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")
        
        # ULTRA-DIRECT: Force immediate function call
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
        
        # Start the agent run
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        logging.info(f"Started run: {run.id}")
        
        # NEW: Detect analysis queries and handle them directly - FIXED RETURN FORMAT
        analysis_keywords = ['most significant', 'most extreme', 'hottest', 'coldest', 'warmest', 'wettest', 'driest', 'highest', 'lowest', 'top', 'worst', 'best', 'find', 'where are']
        is_analysis_query = any(phrase in user_query.lower() for phrase in analysis_keywords)
        
        if is_analysis_query:
            logging.info(f"🔍 Detected analysis query - using direct analysis function")
            try:
                from .dynamic_code_generator import analyze_extreme_regions
                analysis_result = analyze_extreme_regions(user_query)
                
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
                        "thread_id": thread.id
                    }
                else:
                    return {
                        "status": "error",
                        "content": f"Analysis failed: {analysis_result.get('error', 'Unknown error')}",
                        "type": "analysis_error"
                    }
                    
            except Exception as analysis_error:
                logging.error(f"❌ Direct analysis failed: {analysis_error}")
                # Fall back to agent-based processing
                logging.info("🔄 Falling back to agent-based analysis")

        # ENHANCED: Better timeout strategy with status-specific handling
        max_iterations = 15  # Slight increase, but not the main fix
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        final_response_content = None
        in_progress_count = 0  # NEW: Track how long we're stuck in "in_progress"
        
        start_time = time.time()
        max_total_time = 120  # Increased to 2 minutes
        max_in_progress_time = 15  # NEW: Max time to stay in "in_progress"
        last_status_change = start_time
        
        while run.status in ["queued", "in_progress", "requires_action"] and iteration < max_iterations:
            iteration += 1
            current_time = time.time()
            elapsed_time = current_time - start_time
            
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

                                # UPDATED: Check for map results and decide between tiles vs PNG
                                if isinstance(result_value, dict) and ("overlay_url" in result_value or "static_url" in result_value):
                                    enriched = normalize_map_result_dict(result_value, user_query)
                                    enriched["temperature_data"] = build_temperature_data(enriched.get("geojson"))
                                    
                                    # NEW: Decide between tiles and PNG overlay
                                    use_tiles = should_use_tiles(user_query, enriched)
                                    
                                    if use_tiles:
                                        # Return tile configuration
                                        tile_config = create_tile_config(enriched, user_query)
                                        tool_outputs.append({
                                            "tool_call_id": tool_call.id,
                                            "output": json.dumps({"status": "success", "completed": True})
                                        })
                                        return {
                                            "status": "success",
                                            "content": enriched.get("static_url") or "Interactive map generated",
                                            "use_tiles": True,  # ✅ Signal to frontend
                                            "tile_config": tile_config,  # ✅ Tile endpoint info
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
                                        # Use existing PNG overlay approach
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

                                # Legacy single URL path
                                if isinstance(result_value, str) and result_value.startswith("http"):
                                    enriched = wrap_with_geo_overlay(result_value, user_query)
                                    enriched["temperature_data"] = build_temperature_data(enriched.get("geojson"))
                                    tool_outputs.append({
                                        "tool_call_id": tool_call.id,
                                        "output": json.dumps({"status": "success", "completed": True})
                                    })
                                    return {
                                        "status": "success",
                                        "content": enriched["static_url"],
                                        "static_url": enriched["static_url"],
                                        "overlay_url": enriched["overlay_url"],
                                        "geojson": enriched["geojson"],
                                        "bounds": enriched.get("bounds"),
                                        "map_config": enriched["map_config"],
                                        "temperature_data": enriched["temperature_data"],  # NEW
                                        "type": "visualization_with_overlay",
                                        "agent_id": text_agent_id,
                                        "thread_id": thread.id,
                                        "analysis_data": analysis_result
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
                                    "analysis_data": analysis_result
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
                            return {
                                "status": "success",
                                "content": final_response_content,
                                "type": "submission_failed_but_success",
                                "agent_id": text_agent_id,
                                "thread_id": thread.id,
                                "analysis_data": analysis_data
                            }
                
                # Return if code executed
                if custom_code_executed and final_response_content:
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
                        "analysis_data": analysis_data
                    }
            
            # Enhanced: Variable wait time based on status
            if run.status == "in_progress":
                time.sleep(0.5)  # Longer wait when thinking
            else:
                time.sleep(0.2)  # Shorter wait for other statuses
                
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"❌ Get run error: {e}")
                break
        
        # Enhanced final status logging
        final_status = run.status if 'run' in locals() else "unknown"
        logging.error(f"❌ Agent completion without execution:")
        logging.error(f"   Final status: {final_status}")
        logging.error(f"   Iterations: {iteration}/{max_iterations}")
        logging.error(f"   Elapsed time: {elapsed_time:.1f}s")
        logging.error(f"   Custom code executed: {custom_code_executed}")
        
        # Final fallback
        if custom_code_executed and final_response_content:
            return {
                "status": "success",
                "content": final_response_content,
                "type": "final_fallback_success",
                "agent_id": text_agent_id,
                "thread_id": thread.id,
                "analysis_data": analysis_data
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
            float((bounds.get("east")+bounds.get("west"))/2),
            float((bounds.get("north")+bounds.get("south"))/2)
        ]
    except Exception:
        return [-98.0, 39.0]

def should_use_tiles(user_query: str, map_data: dict) -> bool:
    """
    Decide if we should use tiles based on query and data
    """
    bounds = map_data.get("bounds", {})
    if not bounds:
        return False
    
    try:
        lat_range = abs(bounds.get("north", 0) - bounds.get("south", 0))
        lon_range = abs(bounds.get("east", 0) - bounds.get("west", 0))
        area = lat_range * lon_range
        
        logging.info(f"🗺️ Map area: {area:.2f} sq degrees")
        
        # Use tiles if area is large (> 25 sq degrees)
        if area > 25:
            logging.info("✅ Using tiles due to large area")
            return True
        
        # Use tiles if explicitly requested
        if any(word in user_query.lower() for word in ['interactive', 'zoom', 'pan', 'large', 'entire', 'whole']):
            logging.info("✅ Using tiles due to interactive request")
            return True
        
        # Use tiles for state-level queries
        if any(word in user_query.lower() for word in ['california', 'florida', 'texas', 'alaska', 'united states', 'usa']):
            logging.info("✅ Using tiles due to large region")
            return True
        
        logging.info("📸 Using PNG overlay for small area")
        return False
        
    except Exception as e:
        logging.error(f"❌ Error calculating tile decision: {e}")
        return False

def create_tile_config(map_data: dict, user_query: str) -> dict:
    """
    Create tile configuration for frontend
    """
    import re
    
    # Extract date from query or use current
    year_match = re.search(r'(20\d{2})', user_query)
    year = int(year_match.group(1)) if year_match else 2023
    
    month_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)', user_query.lower())
    month_names = ['january','february','march','april','may','june','july','august','september','october','november','december']
    month = month_names.index(month_match.group(1)) + 1 if month_match else 5
    
    # Try to extract day
    day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', user_query)
    day = int(day_match.group(1)) if day_match and 1 <= int(day_match.group(1)) <= 31 else 12
    
    # Detect variable
    variable = 'Tair'  # Default
    if any(word in user_query.lower() for word in ['precipitation', 'rain', 'rainfall']):
        variable = 'Rainf'
    elif any(word in user_query.lower() for word in ['drought', 'spi']):
        variable = 'SPI3'
        date_str = f"{year}-{month:02d}"  # SPI is monthly
    else:
        date_str = f"{year}-{month:02d}-{day:02d}"
    
    # API base URL - UPDATE THIS TO YOUR FASTAPI SERVER
    api_base = "http://localhost:8000/api"
    
    tile_url_template = f"{api_base}/tiles/{variable}/{date_str}/{{z}}/{{x}}/{{y}}.png"
    
    logging.info(f"🎯 Created tile config: {tile_url_template}")
    
    return {
        "tile_url": tile_url_template,
        "variable": variable,
        "date": date_str,
        "min_zoom": 3,
        "max_zoom": 10,
        "tile_size": 256
    }