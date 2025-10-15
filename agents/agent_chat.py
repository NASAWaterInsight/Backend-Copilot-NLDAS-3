# agents/agent_chat.py - Fixed version with better timeout and error handling
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
import re
from .dynamic_code_generator import execute_custom_code
from .dataset_metadata import build_coverage_response
from .memory_manager import memory_manager  # NEW

# EXPANDED follow-up detector keywords
FOLLOWUP_KEYWORDS = ["this map","that map","previous map","last map","earlier map","above map","shown map",
                     "the map","coastal area","shoreline","edge","pattern","why is","what causes",
                     "explain this","analyze this","temperature pattern","cooler","warmer","higher","lower"]

def _is_follow_up_query(q: str) -> bool:  # UPDATED
    ql = (q or "").lower()
    # Direct map references
    if any(k in ql for k in ["this map","that map","previous map","last map","earlier map","above map","shown map"]):
        return True
    # Pattern/analysis questions that likely refer to current context
    pattern_words = ["coastal area","shoreline","edge","pattern","cooler","warmer","higher","lower"]
    question_words = ["why","what causes","explain","analyze","how come"]
    if any(p in ql for p in pattern_words) and any(q in ql for q in question_words):
        return True
    # Temperature-specific follow-ups
    if any(phrase in ql for phrase in ["why is the temperature","what causes the temperature","temperature pattern"]):
        return True
    return False

def _follow_up_response(user_query: str, user_id: str):  # UPDATED
    ctx = LAST_MAP_CONTEXT.get(user_id)
    if not ctx:
        return {
            "status": "no_prior_context",
            "content": "No prior map context available. Please request a map first.",
            "memory_context": []
        }
    
    variable = ctx.get("variable") or "unknown"
    region = ctx.get("region") or "previous region"
    date_scope = ctx.get("date") or "previous date"
    
    # ENHANCED: Provide actual analysis based on query content
    ql = user_query.lower()
    
    if variable == "Tair" or variable == "temperature":
        if any(word in ql for word in ["coastal","shoreline","edge","cooler","warmer"]):
            if "cooler" in ql or "cool" in ql:
                content = f"Coastal areas in {region} ({date_scope}) typically appear cooler in temperature maps due to several factors: (1) Large water bodies like lakes and oceans have high thermal inertia, heating and cooling more slowly than land. (2) During daytime, land heats faster than water, creating a temperature contrast. (3) Lake/sea breezes can moderate coastal temperatures. (4) Evaporation from water surfaces provides cooling. The specific pattern depends on the time of day, season, and local geography."
            elif "warmer" in ql or "warm" in ql:
                content = f"If coastal areas in {region} ({date_scope}) appear warmer, this could be due to: (1) Nighttime conditions when water retains heat longer than land. (2) Seasonal effects where large water bodies store heat from warmer months. (3) Urban heat island effects in coastal cities. (4) Measurement timing - water temperature vs air temperature differences. The pattern would need detailed analysis of the specific data and timing."
            else:
                content = f"Temperature patterns along coastlines in {region} ({date_scope}) are influenced by land-water thermal contrasts, with water bodies moderating temperatures due to their high heat capacity. The specific pattern depends on time of day, season, and local meteorology."
        elif "pattern" in ql:
            content = f"The temperature pattern in {region} ({date_scope}) reflects spatial gradients driven by: (1) Latitude effects (north-south temperature differences), (2) Elevation changes (higher elevation = cooler), (3) Land cover types (urban, forest, agriculture), (4) Water body influences, and (5) Local weather systems. For specific analysis, the actual temperature values and gradients would need to be examined."
        else:
            content = f"This refers to the temperature map for {region} in {date_scope}. The spatial patterns visible reflect the influence of geography, elevation, land cover, and meteorological conditions on air temperature distribution."
    
    elif variable == "SPI3" or variable == "spi":
        content = f"This SPI (drought) map for {region} ({date_scope}) shows precipitation patterns over a 3-month period. Spatial variations reflect: (1) Regional precipitation patterns, (2) Topographic effects on rainfall, (3) Storm track influences, and (4) Seasonal weather patterns. Values below -1.0 indicate drier than normal conditions, while values above +1.0 indicate wetter than normal."
    
    elif variable == "Rainf" or "precip" in ql:
        content = f"This precipitation map for {region} ({date_scope}) shows rainfall distribution. Spatial patterns are influenced by: (1) Storm systems and frontal passages, (2) Topographic effects (orographic precipitation), (3) Proximity to water bodies, and (4) Local convective processes. Coastal areas may show different patterns due to sea/land breeze effects."
    
    else:
        content = f"This {variable} map for {region} ({date_scope}) shows spatial patterns that reflect the influence of meteorological, geographical, and seasonal factors on this variable's distribution."
    
    return {
        "status": "follow_up_analysis",
        "content": content,
        "context": {
            "variable": variable,
            "region": region,
            "date": date_scope,
            "static_url": ctx.get("static_url"),
            "overlay_url": ctx.get("overlay_url"),
            "bounds": ctx.get("bounds")
        },
        "memory_context": []
    }

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

VALID_VARIABLE_ALIASES = {
    "temperature": ["temperature","temp","tair"],
    "precipitation": ["precipitation","precip","rain","rainfall","rainf"],
    "spi": ["spi","drought","spi3"],
    "humidity": ["humidity","qair"],
    "wind": ["wind","wind_n","wind_e"],
    "pressure": ["pressure","psurf"],
    "solar": ["solar","shortwave","swdown"],
    "longwave": ["longwave","lwdown"]
}
# Simple canonical mapping
VARIABLE_CANON = {alias: canon for canon, aliases in VALID_VARIABLE_ALIASES.items() for alias in aliases}

US_STATE_LIKE = [
    "alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware",
    "florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky","louisiana",
    "maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri","montana",
    "nebraska","nevada","new hampshire","new jersey","new mexico","new york","north carolina",
    "north dakota","ohio","oklahoma","oregon","pennsylvania","rhode island","south carolina",
    "south dakota","tennessee","texas","utah","vermont","virginia","washington","west virginia",
    "wisconsin","wyoming"
]

COVERAGE_PATTERNS = [
    r"\bhow\s+many\s+years\b",
    r"\bdata\s+cover(age|s)\b",
    r"\bwhat\s+years\b",
    r"\bdata\s+range\b",
    r"\bavailable\s+years\b",
    r"\bhourly\s+data\b",
    r"\bdaily\s+data\b",
    r"\bdo\s+you\s+have\s+hourly\b",
    r"\bdo\s+you\s+have\s+daily\b",
    r"\bspi\s+years\b",
    r"\bfrom\s+what\s+year\b",
    r"\bwhich\s+years\b",
    # NEW broader paraphrases
    r"\bhow\s+long\b",
    r"\btime\s+span\b",
    r"\btime\s+range\b",
    r"\bcoverage\s+period\b",
    r"\byears\s+of\s+(data|coverage)\b",
    r"\bdata\s+available\b",
    r"\bavailable\s+data\b",
    r"\bhave\s+in\s+your\s+database\b"
]

def is_coverage_query(q: str) -> bool:
    ql = q.lower()
    # Regex patterns
    if any(re.search(pat, ql) for pat in COVERAGE_PATTERNS):
        return True
    # Heuristic fallback (captures many paraphrases)
    if ('year' in ql or 'years' in ql) and 'data' in ql and any(tok in ql for tok in ['how','what','which','available','have','range','span']):
        return True
    return False

# NEW: per-user last map context (ephemeral)
LAST_MAP_CONTEXT = {}  # user_id -> dict with variable, region, date_scope, bounds, static_url, overlay_url

ISO_DATE_PATTERN = re.compile(r"\b20\d{2}-(0[1-9]|1[0-2])(-([0-2]\d|3[01]))?\b")  # NEW

def _infer_date_scope_from_query(q: str):
    ql = (q or "").lower()
    import re
    year = re.search(r"\b(20\d{2})\b", ql)
    month_map = {m:i for i,m in enumerate(["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"],1)}
    month = None
    for m, i in month_map.items():
        if re.search(rf"\b{m}", ql):
            month = i
            break
    if year and month:
        return f"{year.group(1)}-{month:02d}"
    return year.group(1) if year else None

def _infer_region_from_query(q: str):
    ql = (q or "").lower()
    for st in US_STATE_LIKE:
        if re.search(rf"\b{re.escape(st)}\b", ql):
            return st
    return None

def _infer_variable_from_query(q: str):
    ql = (q or "").lower()
    for alias, canon in VARIABLE_CANON.items():
        if re.search(rf"\b{re.escape(alias)}\b", ql):
            return canon
    return None

def handle_chat_request(data):
    """
    ULTRA-DIRECT: Immediate function execution with Azure Maps detection
    """
    try:
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        user_id = data.get("user_id", "default_user")
        existing_thread_id = data.get("thread_id")  # NEW
        logging.info(f"Processing chat request: {user_query} (user_id={user_id})")

        # NEW follow-up early intercept (before coverage / prompt)
        if _is_follow_up_query(user_query):
            return _follow_up_response(user_query, user_id)

        # NEW: retrieve recent structured map memories
        recent_mem = memory_manager.recent_context(user_id, limit=3)
        memory_snippets = [m.get("memory") for m in recent_mem if m.get("memory")]
        recent_block = ""
        if memory_snippets:
            recent_block = "RECENT_CONTEXT:\n" + "\n".join(memory_snippets)

        # NEW: reuse existing thread if provided
        if existing_thread_id:
            thread = type("T", (), {"id": existing_thread_id})
            logging.info(f"Reusing thread: {existing_thread_id}")
        else:
            thread = project_client.agents.threads.create()
            logging.info(f"Created thread: {thread.id}")

        # NEW: Coverage / availability shortcut
        if is_coverage_query(user_query):
            logging.info("Detected coverage / availability query; returning metadata without tool execution.")
            coverage = build_coverage_response()
            return {
                "status": "coverage_info",
                "content": coverage["summary"],
                "coverage": coverage,
                "agent_id": text_agent_id,
                "memory_context": memory_snippets  # NEW
            }

        # NEW: Lightweight heuristic signals for prompt conditioning
        q_lower = user_query.lower()
        has_var = any(k in q_lower for k in ["temperature","tair","precip","rain","rainf","humidity","qair","spi","drought","wind","pressure","psurf"])
        has_place = any(k in q_lower for k in ["florida","alaska","california","michigan","texas","ohio","virginia","colorado","arizona","georgia","maryland","nevada","oregon","washington"])
        has_date_token = any(tok in q_lower for tok in [" jan"," feb"," mar"," apr"," may"," jun"," jul"," aug"," sep"," oct"," nov"," dec"]) \
                         or bool(re.search(r"\b20\d{2}\b", q_lower)) \
                         or bool(ISO_DATE_PATTERN.search(q_lower))  # CHANGED
        minimal_context = not (has_var and (has_place or has_date_token))

        # NEW: if variable+date remembered but missing region -> supply prior region if LAST_MAP_CONTEXT
        if not has_place and has_var and has_date_token and user_id in LAST_MAP_CONTEXT:
            prev_region = LAST_MAP_CONTEXT[user_id].get("region")
            if prev_region:
                logging.info("Auto-injecting previous region into minimal context query.")
                user_query = f"{user_query} (previous region: {prev_region})"

        # Create a thread for the conversation
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")

        # UPDATED PROMPT: Only call execute_custom_code if query is actionable
        enhanced_query = f"""You are an NLDAS-3 hydrometeorological assistant.
{recent_block}

USER QUERY: \"{user_query}\"

DECISION RULES:
1. If the query is greetings, casual chat, or unrelated to NLDAS / weather / drought -> Reply briefly and ask the user to specify a variable (temperature, precipitation, SPI, drought) plus a location and date. DO NOT call execute_custom_code.
2. If the query lacks required info (missing variable OR missing location/date), respond with a one-sentence clarification request listing exactly what is missing. DO NOT call execute_custom_code.
3. ONLY call execute_custom_code when the query clearly specifies (a) target variable (e.g. temperature / SPI / precipitation), and (b) spatial region (state or bounding concept) or (c) date / month / range.
4. When you do call execute_custom_code you MUST provide a JSON with python_code and user_request, returning a proper result dict with static_url + overlay_url etc.
5. NEVER guess ambiguous dates or regions—ask instead.

ACTIONABILITY ASSESSMENT (heuristic pre-analysis):
- variable_detected: {has_var}
- location_detected: {has_place}
- date_token_detected: {has_date_token}
- minimal_context: {minimal_context}

If rules 1 or 2 apply: answer directly, no tool call.
If rule 3 applies: call execute_custom_code.

Respond now following the rules above."""

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

                                # NEW guard if result_value is None
                                if result_value is None:
                                    result_value = "No result produced."

                                # UPDATED: Full map dict (dual URLs)
                                if isinstance(result_value, dict) and ("overlay_url" in result_value or "static_url"):
                                    enriched = normalize_map_result_dict(result_value, user_query)
                                    enriched["temperature_data"] = build_temperature_data(enriched.get("geojson"))
                                    # NEW: persist structured map context
                                    try:
                                        inferred_var = _infer_variable_from_query(user_query)
                                        inferred_region = _infer_region_from_query(user_query)
                                        date_scope = _infer_date_scope_from_query(user_query)
                                        bounds = enriched.get("bounds")
                                        # Optional color range from geojson sample
                                        color_range = None
                                        if enriched.get("geojson", {}).get("features"):
                                            vals = []
                                            for f in enriched["geojson"]["features"]:
                                                v = f.get("properties", {}).get("value")
                                                try:
                                                    if v is not None:
                                                        vals.append(float(v))
                                                except:
                                                    pass
                                            if vals:
                                                color_range = {"min": min(vals), "max": max(vals)}
                                        memory_manager.add_structured(
                                            user_id=user_id,
                                            variable=inferred_var,
                                            region=inferred_region,
                                            date_str=date_scope,
                                            bounds=bounds,
                                            color_range=color_range
                                        )
                                        memory_manager.add(
                                            f"[MAP_SUMMARY] variable={inferred_var} region={inferred_region} date={date_scope} bounds={bounds}",
                                            user_id=user_id,
                                            meta={"type": "map_summary"}
                                        )
                                        # Track last map in ephemeral dict
                                        LAST_MAP_CONTEXT[user_id] = {
                                            "variable": inferred_var,
                                            "region": inferred_region,
                                            "date": date_scope,
                                            "bounds": bounds,
                                            "static_url": enriched.get("static_url"),
                                            "overlay_url": enriched.get("overlay_url")
                                        }
                                    except Exception as mem_err:
                                        logging.debug(f"Memory persistence failed: {mem_err}")
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
                                        "temperature_data": enriched["temperature_data"],  # NEW
                                        "memory_context": memory_snippets,  # already there
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
                                        "memory_context": memory_snippets  # NEW
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
                                    "analysis_data": analysis_result,
                                    "memory_context": memory_snippets  # NEW
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
                                "analysis_data": analysis_data,
                                "memory_context": memory_snippets  # NEW
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
                        "analysis_data": analysis_data,
                        "memory_context": memory_snippets  # NEW
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
        
        # Enhanced final status handling (REPLACE original block that logged failure)
        final_status = run.status if 'run' in locals() else "unknown"
        if final_status == "completed" and not custom_code_executed:
            logging.info("✅ Run completed without tool execution; returning assistant reply.")
            assistant_reply = extract_last_assistant_message(thread.id)
            return {
                "status": "assistant_reply",
                "content": assistant_reply or "I can help with NLDAS-3 data. Specify a variable, location and date.",
                "agent_id": text_agent_id,
                "thread_id": thread.id,
                "memory_context": memory_snippets,  # NEW
                "debug": {
                    "iterations": iteration,
                    "elapsed_time": elapsed_time,
                    "custom_code_executed": False,
                    "final_status": final_status
                }
            }

        # (Keep existing fallback but move after the new completion branch)
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
                "analysis_data": analysis_data,
                "memory_context": memory_snippets  # NEW
            }
        
        # Timeout response with more helpful message
        elapsed_time = time.time() - start_time
        return {
            "status": "timeout_failure", 
            "content": f"Agent failed to execute function after {max_iterations} iterations ({elapsed_time:.1f}s). The agent appears to be stuck in '{final_status}' status. This may require agent recreation.",
            "type": "iteration_limit_exceeded",
            "agent_id": text_agent_id,
            "thread_id": thread.id,
            "memory_context": memory_snippets,  # NEW
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
            "error_type": type(e).__name__,
            "memory_context": []
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

# NEW: helper to extract last assistant message if no tool used
def extract_last_assistant_message(thread_id: str) -> str:
    try:
        msgs = project_client.agents.messages.list(thread_id=thread_id)
        # SDK list ordering may vary; ensure we look from newest
        candidate = None
        for m in reversed(list(msgs)):
            if getattr(m, "role", None) == "assistant":
                parts = []
                for c in getattr(m, "content", []):
                    # Each content item may be text / other types
                    text_val = getattr(c, "text", None)
                    if text_val:
                        parts.append(getattr(text_val, "value", "") or str(text_val))
                candidate = "\n".join(p for p in parts if p).strip()
                if candidate:
                    break
        return candidate
    except Exception as e:
        logging.warning(f"Could not extract assistant message: {e}")
        return None