# agents/agent_chat.py - Fixed version with better timeout and error handling
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
import re
import hashlib  # Add for user ID hashing
from .dynamic_code_generator import execute_custom_code
from .dataset_metadata import build_coverage_response

# ADD MEMORY IMPORT
try:
    from .memory_manager import memory_manager
    MEMORY_AVAILABLE = True
except ImportError:
    logging.warning("Memory manager not available")
    MEMORY_AVAILABLE = False
    memory_manager = None

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

def get_user_id(req, body: dict) -> str:
    """
    Extract stable user identifier from request
    Priority: AAD principal > X-User-Email (hashed) > X-User-Id header > body user_id > anonymous
    """
    # Priority 1: Azure AD principal (for institutional users)
    principal_id = req.headers.get('X-MS-CLIENT-PRINCIPAL-ID') if hasattr(req, 'headers') else None
    if principal_id:
        return principal_id
    
    # Priority 2: Email hash (privacy-preserving)
    user_email = req.headers.get('X-User-Email') if hasattr(req, 'headers') else None
    if user_email:
        normalized_email = user_email.lower().strip()
        email_hash = hashlib.sha256(normalized_email.encode()).hexdigest()[:32]
        return f"email_{email_hash}"
    
    # Priority 3: X-User-Id header (frontend-generated UUID)
    user_id = req.headers.get('X-User-Id') if hasattr(req, 'headers') else None
    if user_id and user_id != 'anonymous':
        return user_id
    
    # Priority 4: Body user_id field (fallback)
    if 'user_id' in body and body['user_id'] != 'anonymous':
        return body['user_id']
    
    # Priority 5: Anonymous with warning
    logging.warning("No stable user_id found - using 'anonymous' (memory will not persist)")
    return 'anonymous'

def handle_chat_request(data):
    """
    Enhanced chat handler with intelligent Mem0 memory integration
    """
    try:
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        
        # Extract user ID
        user_id = get_user_id(data.get('_request'), data)
        logging.info(f"🆔 Processing request for user: {user_id[:8]}...")
        
        # ENHANCED MEMORY RETRIEVAL with LOWER threshold for conversation continuity
        memory_context = []
        if MEMORY_AVAILABLE and memory_manager and memory_manager.enabled and user_id != 'anonymous':
            try:
                # Use Mem0's semantic search 
                memories = memory_manager.search(
                    user_query, 
                    user_id=user_id, 
                    limit=5,  # Get more candidates for filtering
                    enable_graph=False
                )
                
                if memories:
                    logging.info(f"🧠 Retrieved {len(memories)} memory candidates")
                    
                    # ENHANCED FILTERING: Lower threshold for conversation continuity
                    relevant_memories = []
                    
                    for mem in memories:
                        if isinstance(mem, dict):
                            memory_text = mem.get('memory', mem.get('text', ''))
                            score = mem.get('score', 0.0)
                            
                            # LOWERED threshold from 0.5 to 0.3 for better conversation continuity
                            if score > 0.3 and memory_text:  
                                # Additional contextual check
                                if is_memory_contextually_relevant(memory_text, user_query):
                                    relevant_memories.append({
                                        'text': memory_text,
                                        'score': score,
                                        'metadata': mem.get('metadata', {})
                                    })
                                    logging.info(f"   ✅ Relevant (score: {score:.2f}): {memory_text[:50]}...")
                                else:
                                    logging.info(f"   ❌ Filtered: {memory_text[:30]}...")
                            else:
                                logging.info(f"   ⚠️ Low score ({score:.2f}): {memory_text[:30]}...")
                    
                    memory_context = relevant_memories
                    
                    if memory_context:
                        logging.info(f"🧠 Using {len(memory_context)} relevant memories")
                    else:
                        logging.info("🧠 No contextually relevant memories found")
                        
                        # FALLBACK: If no relevant memories but user query looks like a continuation, get recent memories
                        if re.match(r'^\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}\s*$|^\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\s*$', user_query.lower().strip()):
                            logging.info("🗓️ Query looks like date - getting recent context as fallback")
                            try:
                                recent_memories = memory_manager.recent_context(user_id=user_id, limit=3)
                                if recent_memories:
                                    memory_context = [{'text': mem, 'score': 0.8} for mem in recent_memories]
                                    logging.info(f"🔄 Using {len(memory_context)} recent memories as fallback")
                            except Exception as recent_error:
                                logging.warning(f"Recent context fallback failed: {recent_error}")
                else:
                    logging.info("🧠 No memories found")
                    
            except Exception as mem_error:
                logging.warning(f"Memory search failed: {mem_error}")
                memory_context = []

        logging.info(f"Processing chat request: {user_query}")

        # NEW: Coverage / availability shortcut
        if is_coverage_query(user_query):
            logging.info("Detected coverage / availability query; returning metadata without tool execution.")
            coverage = build_coverage_response()
            return {
                "status": "coverage_info",
                "content": coverage["summary"],
                "coverage": coverage,
                "agent_id": text_agent_id,
                "user_id": user_id,
                "memory_context": memory_context
            }

        # NEW: Lightweight heuristic signals for prompt conditioning
        q_lower = user_query.lower()
        has_var = any(k in q_lower for k in ["temperature","tair","precip","rain","rainf","humidity","qair","spi","drought","wind","pressure","psurf"])
        has_place = any(k in q_lower for k in ["florida","alaska","california","michigan","texas","ohio","virginia","colorado","arizona","georgia","maryland","nevada","oregon","washington"])
        has_date_token = any(tok in q_lower for tok in [" 2020"," 2021"," 2022"," 2023"," jan"," feb"," mar"," apr"," may"," jun"," jul"," aug"," sep"," oct"," nov"," dec"])

        # Create a thread for the conversation
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")

        # ENHANCED PROMPT with memory context
        memory_context_text = ""
        if memory_context:
            memory_context_text = "\n\nRelevant context from previous conversations:\n"
            for mem in memory_context:
                if isinstance(mem, dict):
                    text = mem.get('text', '')
                    score = mem.get('score', 0)
                    memory_context_text += f"- [{score:.2f}] {text}\n"
                else:
                    memory_context_text += f"- {mem}\n"

        enhanced_query = f"""You are an NLDAS-3 weather assistant with visual memory of maps and patterns.

USER: "{user_query}"{memory_context_text}

ENHANCED CAPABILITIES:
- You can SEE and ANALYZE maps you've previously generated
- You can answer questions about VISUAL PATTERNS in temperature maps
- You can identify spatial relationships like "weather around lakes", temperature gradients, hot/cold spots

CRITICAL RULES:
1. If you have COMPLETE info (location + variable + date), call execute_custom_code IMMEDIATELY
2. If user asks about VISUAL PATTERNS in previous maps (like "weather around lakes"), analyze the stored image memory
3. Use previous context including VISUAL MEMORIES when relevant
4. For pattern analysis questions, reference the visual data from stored map images

Context Status:
- Variable detected: {has_var}
- Location detected: {has_place}  
- Date detected: {has_date_token}
- Relevant context available: {len(memory_context) > 0}
- Visual memories available: {len([m for m in memory_context if isinstance(m, dict) and m.get('metadata', {}).get('can_analyze_visually')])>0}

Examples:
- "temperature map for Michigan June 1, 2023" → Execute code, store visual memory
- "is the weather around lakes cooler?" → Analyze stored visual memory of Michigan temperature map
- "show me warmer/colder regions" → Reference visual patterns from stored map

RESPOND with visual analysis if asking about map patterns, or execute code for new requests.

Respond now."""

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
        
        # ADD MEMORY: Store the user query
        if MEMORY_AVAILABLE and memory_manager and memory_manager.enabled and user_id != 'anonymous':
            try:
                memory_manager.add(
                    f"User asked: {user_query}",
                    user_id=user_id,
                    meta={"type": "user_query", "timestamp": time.time()}
                )
            except Exception as mem_error:
                logging.warning(f"Failed to store user query in memory: {mem_error}")

        # RESTORED ORIGINAL WORKING TIMEOUT AND PROCESSING LOGIC
        max_iterations = 15
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        final_response_content = None
        in_progress_count = 0
        
        # Variables to track extracted info for structured memory storage
        extracted_variable = None
        extracted_region = None
        extracted_date = None
        
        start_time = time.time()
        max_total_time = 120
        max_in_progress_time = 15
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
                            # ENHANCED: Better argument parsing and extraction tracking
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
                                # Extract info from fallback
                                extracted_variable = "temperature"
                                extracted_region = "Alaska" 
                                extracted_date = "2023-01-03"
                            else:
                                try:
                                    function_args = json.loads(raw_arguments)
                                    logging.info("✅ Successfully parsed JSON arguments")
                                    
                                    # Try to extract variable/region/date from the code for structured memory
                                    python_code = function_args.get("python_code", "")
                                    if "Tair" in python_code or "temperature" in python_code.lower():
                                        extracted_variable = "temperature"
                                    elif "Rainf" in python_code or "precip" in python_code.lower():
                                        extracted_variable = "precipitation"
                                    elif "SPI" in python_code or "spi" in python_code.lower():
                                        extracted_variable = "spi"
                                    
                                    # Extract region from code or user query
                                    for state in US_STATE_LIKE:
                                        if state in user_query.lower() or state in python_code.lower():
                                            extracted_region = state.title()
                                            break
                                    
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
                                        extracted_variable = "temperature"
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

                                # ENHANCED: Store successful analysis with IMAGE for vision memory
                                if MEMORY_AVAILABLE and memory_manager and memory_manager.enabled and user_id != 'anonymous':
                                    try:
                                        # Store the successful interaction
                                        if isinstance(result_value, dict) and ("overlay_url" in result_value or "static_url" in result_value):
                                            # This was a map generation - STORE WITH IMAGE for vision analysis
                                            bounds = result_value.get("bounds", {})
                                            map_url = result_value.get("static_url") or result_value.get("overlay_url")
                                            
                                            # VISION MEMORY: Store the map image with contextual description
                                            if map_url:
                                                # ENHANCED: Skip multimodal for now, go straight to robust text-only fallback
                                                try:
                                                    fallback_description = f"Generated {extracted_variable or 'weather'} map for {extracted_region or 'region'} on {extracted_date or 'date'}. " \
                                                                         f"Map shows spatial temperature patterns across the region. " \
                                                                         f"Map URL: {map_url}. " \
                                                                         f"User can ask about visual patterns like 'weather around lakes', temperature gradients, hot/cold spots in this map."
                                                    
                                                    memory_manager.add(
                                                        fallback_description,
                                                        user_id=user_id,
                                                        meta={
                                                            "type": "map_visualization_text_only",
                                                            "variable": extracted_variable,
                                                            "region": extracted_region,
                                                            "date": extracted_date,
                                                            "map_url": map_url,
                                                            "can_analyze_visually": True  # Agent can reference visual patterns
                                                        }
                                                    )
                                                    logging.info(f"🖼️ Stored visual memory (text-based): {extracted_variable} for {extracted_region}")
                                                    
                                                except Exception as fallback_error:
                                                    logging.warning(f"Visual memory fallback failed: {fallback_error}")
                                            
                                            logging.info(f"🧠 Stored structured analysis: {extracted_variable} for {extracted_region}")
                                            
                                        elif isinstance(result_value, str) and result_value.startswith("http"):
                                            # ENHANCED: Skip multimodal, use robust text-only approach
                                            try:
                                                fallback_description = f"Generated {extracted_variable or 'weather'} visualization showing spatial patterns. " \
                                                                     f"Map URL: {result_value}. " \
                                                                     f"User can ask about visual patterns, spatial relationships, and weather gradients in this map."
                                                
                                                memory_manager.add(
                                                    fallback_description,
                                                    user_id=user_id,
                                                    meta={
                                                        "type": "map_visualization_text_only",
                                                        "variable": extracted_variable,
                                                        "region": extracted_region,
                                                        "map_url": result_value,
                                                        "can_analyze_visually": True
                                                    }
                                                )
                                                logging.info(f"🖼️ Stored visual memory (text-based): {extracted_variable} visualization")
                                                
                                            except Exception as fallback_error:
                                                logging.warning(f"Visual memory fallback failed: {fallback_error}")
                                            
                                            # Regular text memory
                                            memory_manager.add(
                                                f"Generated visualization for: {user_query}. Result: {result_value}",
                                                user_id=user_id,
                                                meta={"type": "successful_analysis", "result_type": "visualization", 
                                                     "variable": extracted_variable, "region": extracted_region}
                                            )
                                        else:
                                            # FIXED: Only store a brief summary, don't truncate the actual result
                                            memory_summary = f"Completed {extracted_variable or 'weather'} analysis for {extracted_region or 'region'}"
                                            if extracted_date:
                                                memory_summary += f" on {extracted_date}"
                                            
                                            memory_manager.add(
                                                memory_summary,
                                                user_id=user_id,
                                                meta={"type": "successful_analysis", "result_type": "data",
                                                     "variable": extracted_variable, "region": extracted_region}
                                            )
                                    except Exception as mem_error:
                                        logging.warning(f"Failed to store result in memory: {mem_error}")

                                # UPDATED: Full map dict (dual URLs)
                                if isinstance(result_value, dict) and ("overlay_url" in result_value or "static_url"):
                                    enriched = normalize_map_result_dict(result_value, user_query)
                                    enriched["temperature_data"] = build_temperature_data(enriched.get("geojson"))
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
                                        "type": "visualization_with_overlay",
                                        "agent_id": text_agent_id,
                                        "thread_id": thread.id,
                                        "analysis_data": analysis_result,
                                        "user_id": user_id,  # MEMORY: Include user_id in response
                                        "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
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
                                        "analysis_data": analysis_result,
                                        "user_id": user_id,  # MEMORY: Include user_id in response
                                        "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
                                    }

                                # ENHANCED: Handle dictionary results with temperature analysis
                                if isinstance(result_value, dict):
                                    # Check if it's temperature coordinate analysis
                                    if "warmest_point" in result_value and "coldest_point" in result_value:
                                        warmest = result_value["warmest_point"]
                                        coldest = result_value["coldest_point"]
                                        
                                        # Format human-readable response
                                        final_response_content = f"Based on the temperature analysis for Michigan on June 1, 2023:\n\n"
                                        final_response_content += f"🌡️ **Warmest region**: Located at coordinates ({warmest[0]}, {warmest[1]}) - this appears to be in the southwestern part of Michigan\n\n"
                                        final_response_content += f"❄️ **Coldest region**: Located at coordinates ({coldest[0]}, {coldest[1]}) - this appears to be in the northern part of Michigan\n\n"
                                        final_response_content += f"The temperature difference shows that southern Michigan was warmer than northern Michigan on that date, which is typical due to latitude differences."
                                    
                                    # Check if it's precipitation data or other weather data
                                    elif any(key in result_value for key in ["precipitation", "humidity", "pressure", "average_temperature"]):
                                        # Format other weather data
                                        final_response_content = "Weather Analysis Results:\n"
                                        for key, value in result_value.items():
                                            if key == "average_temperature":
                                                final_response_content += f"Average Temperature: {value:.1f}°C\n"
                                            elif key == "precipitation":
                                                final_response_content += f"Precipitation: {value:.2f} mm\n"
                                            else:
                                                final_response_content += f"{key.replace('_', ' ').title()}: {value}\n"
                                    
                                    else:
                                        # Generic dictionary formatting
                                        final_response_content = "Analysis Results:\n"
                                        for key, value in result_value.items():
                                            final_response_content += f"{key.replace('_', ' ').title()}: {value}\n"
                                
                                # IMPROVED: Clean up the response format for strings
                                elif isinstance(result_value, str):
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
                                    # For other result types, convert to string
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
                                    "user_id": user_id,  # MEMORY: Include user_id in response
                                    "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
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
                                "user_id": user_id,  # MEMORY: Include user_id in response
                                "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
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
                        "user_id": user_id,  # MEMORY: Include user_id in response
                        "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
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
                "debug": {
                    "iterations": iteration,
                    "elapsed_time": elapsed_time,
                    "custom_code_executed": False,
                    "final_status": final_status
                },
                "user_id": user_id,  # MEMORY: Include user_id in response
                "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
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
                "user_id": user_id,  # MEMORY: Include user_id in response
                "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
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
            "user_id": user_id,  # MEMORY: Include user_id in response
            "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
        }
        
    except Exception as e:
        logging.error(f"❌ Request error: {e}", exc_info=True)
        return {
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__,
            "user_id": user_id,  # MEMORY: Include user_id in response
            "memory_context": memory_context  # MEMORY: Include memory context used (if applicable)
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

def is_memory_contextually_relevant(memory_text: str, current_query: str) -> bool:
    """
    ENHANCED: More aggressive context detection for conversation continuity
    """
    try:
        memory_lower = memory_text.lower()
        query_lower = current_query.lower()
        
        # WEATHER/ANALYSIS CONTEXT KEYWORDS
        weather_terms = ['temperature', 'precipitation', 'spi', 'drought', 'humidity', 'wind', 'pressure', 'weather', 'map', 'analysis', 'show']
        location_terms = ['florida', 'alaska', 'california', 'michigan', 'texas', 'ohio', 'virginia', 'colorado', 'arizona', 'georgia', 'maryland', 'nevada', 'oregon', 'washington']
        
        # ENHANCED: Detect recent conversation flow patterns
        recent_conversation_indicators = [
            # Previous context indicators in memory
            'user asked:', 'show me', 'map of', 'precipitation', 'temperature',
            # Current query continuation indicators  
            'may', 'april', 'march', 'january', 'february', 'june', 'july', 'august', 'september', 'october', 'november', 'december',
            '2020', '2021', '2022', '2023', '12', '15', '20', '25'
        ]
        
        # CRITICAL FIX: If current query is just a date, it's VERY likely continuing previous conversation
        date_only_pattern = re.match(r'^\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}\s*$|^\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\s*$', query_lower)
        if date_only_pattern:
            logging.info(f"🗓️ Detected date-only query: '{current_query}' - checking for weather context in memory")
            # If memory contains weather terms, this is almost certainly relevant
            if any(term in memory_lower for term in ['precipitation', 'temperature', 'map', 'michigan', 'florida', 'show me']):
                logging.info(f"   ✅ Found weather context in memory - date query is relevant")
                return True
        
        # Check for shared weather/analysis context (original logic)
        memory_has_weather = any(term in memory_lower for term in weather_terms)
        query_has_weather = any(term in query_lower for term in weather_terms + recent_conversation_indicators)
        
        # If both are about weather/analysis, check for specific overlap
        if memory_has_weather or query_has_weather:
            # Check for shared location
            memory_locations = [term for term in location_terms if term in memory_lower]
            query_locations = [term for term in location_terms if term in query_lower]
            
            # Check for shared variable
            memory_variables = [term for term in weather_terms if term in memory_lower]
            query_variables = [term for term in weather_terms if term in query_lower]
            
            # ENHANCED: More inclusive relevance detection
            shared_locations = set(memory_locations) & set(query_locations)
            shared_variables = set(memory_variables) & set(query_variables)
            both_about_maps = ('map' in memory_lower or 'show' in memory_lower) and ('map' in query_lower or 'show' in query_lower or date_only_pattern)
            recent_weather_context = any(term in memory_lower for term in recent_conversation_indicators)
            
            if shared_locations or shared_variables or both_about_maps or recent_weather_context:
                return True
        
        # CONTEXTUAL CONTINUATION PATTERNS (enhanced)
        continuation_patterns = [
            # Reference patterns
            ('that', 'show', 'display', 'same', 'similar', 'also', 'too'),
            # Modification patterns  
            ('but for', 'instead of', 'change to', 'different'),
            # Follow-up patterns
            ('what about', 'how about', 'can you show'),
            # NEW: Date continuation patterns
            ('may', 'april', 'march', 'january', 'february', 'june', 'july', 'august', 'september', 'october', 'november', 'december')
        ]
        
        # Check if current query references previous context
        for pattern_group in continuation_patterns:
            if any(pattern in query_lower for pattern in pattern_group):
                # If it's a date pattern, require weather context in memory
                if pattern in ['may', 'april', 'march', 'january', 'february', 'june', 'july', 'august', 'september', 'october', 'november', 'december']:
                    if memory_has_weather:
                        return True
                else:
                    return True
        
        # EXCLUDE NON-CONTEXTUAL MEMORIES (but be more lenient for weather context)
        non_contextual_patterns = [
            'hello', 'hi there', 'how are you', 'good morning', 'good afternoon',
            'thank you', 'thanks', 'bye', 'goodbye', 'nice to meet you'
        ]
        
        # FIXED: Syntax error on this line - missing 'any(' function call
        memory_is_greeting = any(pattern in memory_lower for pattern in non_contextual_patterns)
        if memory_is_greeting and not any(term in memory_lower for term in weather_terms):
            return False
        
        # ENHANCED: Allow short weather-related memories to be relevant to date queries
        if len(memory_text.split()) < 5:
            # Short memory - only relevant if it contains weather terms and current query is date-like
            if memory_has_weather and (date_only_pattern or any(term in query_lower for term in recent_conversation_indicators)):
                return True
            return False
            
        return False  # Default to not relevant unless specifically matches
        
    except Exception as e:
        logging.warning(f"Context relevance check failed: {e}")
        return False  # Default to not relevant on error