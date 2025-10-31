# agents/agent_chat.py - REVISED VERSION with proper memory integration
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


def build_structured_memory_context(recent_memories, relevant_memories, user_id: str) -> dict:
    """
    Build structured memory context that the agent can reliably parse
    
    Returns:
        dict with 'text' (formatted string) and 'metadata' (structured data)
    """
    if not recent_memories and not relevant_memories:
        logging.info(f"📭 No memory found for user {user_id[:8]}...")
        return {
            'text': '',
            'metadata': {
                'has_memory': False,
                'last_variable': None,
                'last_region': None,
                'last_date': None
            }
        }
    
    logging.info(f"🧠 Building memory context for user {user_id[:8]}...")
    
    # Extract structured information
    metadata = {
        'has_memory': True,
        'last_variable': None,
        'last_region': None,
        'last_date': None,
        'memory_count': len(recent_memories) + len(relevant_memories)
    }
    
    context_lines = ["=" * 60, "MEMORY CONTEXT (Your Previous Interactions):", "=" * 60]
    
    # Process recent memories
    if recent_memories:
        context_lines.append("\n📋 RECENT QUERIES:")
        for idx, mem in enumerate(recent_memories[:3], 1):
            if isinstance(mem, dict):
                mem_text = mem.get('memory', str(mem))
                mem_meta = mem.get('metadata', {})
                
                # Extract structured data from most recent memory
                if idx == 1:
                    if 'variable' in mem_meta:
                        metadata['last_variable'] = mem_meta['variable']
                    if 'region' in mem_meta:
                        metadata['last_region'] = mem_meta['region']
                    if 'date_str' in mem_meta:
                        metadata['last_date'] = mem_meta['date_str']
            else:
                mem_text = str(mem)
            
            context_lines.append(f"  {idx}. {mem_text}")
            
            # Try to extract from text if metadata not available
            if idx == 1 and not metadata['last_variable']:
                import re
                # Extract variable
                if 'Rainf' in mem_text or 'precipitation' in mem_text.lower():
                    metadata['last_variable'] = 'Rainf'
                elif 'Tair' in mem_text or 'temperature' in mem_text.lower():
                    metadata['last_variable'] = 'Tair'
                elif 'SPI3' in mem_text or 'drought' in mem_text.lower():
                    metadata['last_variable'] = 'SPI3'
                
                # Extract date (YYYY-MM-DD or YYYY-MM)
                date_match = re.search(r'(\d{4}-\d{2}(?:-\d{2})?)', mem_text)
                if date_match:
                    metadata['last_date'] = date_match.group(1)
                
                # Extract region
                regions = ['florida', 'california', 'maryland', 'texas', 'alaska', 'michigan']
                for region in regions:
                    if region in mem_text.lower():
                        metadata['last_region'] = region
                        break
    
    # Process relevant memories
    if relevant_memories:
        context_lines.append("\n🔍 RELEVANT CONTEXT:")
        for idx, mem in enumerate(relevant_memories[:3], 1):
            if isinstance(mem, dict):
                mem_text = mem.get('memory', '')
                if mem_text:
                    context_lines.append(f"  {idx}. {mem_text}")
            else:
                context_lines.append(f"  {idx}. {str(mem)}")
    
    # Add explicit extraction section
    context_lines.append("\n" + "=" * 60)
    context_lines.append("EXTRACTED PARAMETERS FROM MEMORY:")
    if metadata['last_variable']:
        context_lines.append(f"  • Variable: {metadata['last_variable']}")
    if metadata['last_region']:
        context_lines.append(f"  • Region: {metadata['last_region']}")
    if metadata['last_date']:
        context_lines.append(f"  • Date: {metadata['last_date']}")
    context_lines.append("=" * 60)
    
    memory_text = "\n".join(context_lines)
    
    logging.info(f"✅ Memory context built:")
    logging.info(f"   - Variable: {metadata['last_variable']}")
    logging.info(f"   - Region: {metadata['last_region']}")
    logging.info(f"   - Date: {metadata['last_date']}")
    
    return {
        'text': memory_text,
        'metadata': metadata
    }


def construct_enhanced_query(user_query: str, memory_context: dict) -> str:
    """
    Construct query with explicit memory instructions for the agent
    """
    memory_text = memory_context.get('text', '')
    metadata = memory_context.get('metadata', {})
    
    if not metadata.get('has_memory'):
        # No memory - just return the query
        return f"""
NEW USER - NO PREVIOUS CONTEXT

Current Query: {user_query}

Instructions: This is a new user with no previous interactions. Process the query directly and ask for any missing information.
"""
    
    # Has memory - provide explicit instructions
    enhanced = f"""
{memory_text}

CURRENT QUERY: {user_query}

MEMORY-AWARE INSTRUCTIONS:
1. Check if current query references previous context:
   - Words like "same", "that", "this", "again", "also" indicate memory usage
   - Missing parameters (date/region) may be in memory above

2. Apply memory when appropriate:
   - "show the same for California" → Use previous variable + date, new region (California)
   - "on March 15" → Use previous variable + region, new date (March 15)
   - "show precipitation" → Use previous date + region if not specified, new variable

3. Extract from MEMORY CONTEXT section if needed:
   - Last variable used: {metadata.get('last_variable', 'NONE')}
   - Last region analyzed: {metadata.get('last_region', 'NONE')}
   - Last date queried: {metadata.get('last_date', 'NONE')}

4. Decision process:
   a) Extract explicit parameters from CURRENT QUERY
   b) For missing parameters, check EXTRACTED PARAMETERS FROM MEMORY
   c) If you have all needed info (variable, region, date), call execute_custom_code IMMEDIATELY
   d) If still missing required info, ask user

CRITICAL: Do NOT ask for information that is clearly available in memory context above.

Now process the CURRENT QUERY using this memory context.
"""
    
    return enhanced


def determine_optimal_zoom_level(bounds: dict) -> int:
    """Area-based zoom selection for optimal tile count"""
    import mercantile
    
    lat_span = bounds["north"] - bounds["south"]
    lng_span = bounds["east"] - bounds["west"]
    area = lat_span * lng_span
    
    logging.info(f"🗺️ Region area: {area:.2f} sq degrees ({lat_span:.2f}° × {lng_span:.2f}°)")
    
    # California override
    if (31 <= bounds["south"] <= 33 and 
        41 <= bounds["north"] <= 43 and 
        -126 <= bounds["west"] <= -124 and 
        -115 <= bounds["east"] <= -113):
        logging.info("🗺️ Detected California - using hardcoded zoom 7")
        return 7
    
    # Linear scaling: 2.5 tiles per 100 square degrees
    TILES_PER_100_SQ_DEGREES = 2.5
    target_tiles = (area / 100.0) * TILES_PER_100_SQ_DEGREES
    target_tiles = max(6, min(300, target_tiles))
    
    logging.info(f"🎯 Target tiles: {target_tiles:.0f}")
    
    # Find zoom level with closest tile count
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
            
            if diff < best_diff:
                best_diff = diff
                best_zoom = zoom
                best_count = total_tiles
                
        except Exception as e:
            logging.warning(f"  Zoom {zoom}: Failed - {e}")
            continue
    
    logging.info(f"✅ Selected zoom {best_zoom}: {best_count} tiles")
    return best_zoom


def create_tile_config(map_data: dict, user_query: str, date_info: dict = None) -> dict:
    """Create tile configuration from either raw data or pre-computed data"""
    import re
    import mercantile
    
    logging.info(f"🔍 create_tile_config called for: {user_query}")
    
    # CRITICAL: ONLY use metadata
    if not date_info or date_info.get("error"):
        logging.error(f"❌ No date_info provided: {date_info}")
        return {"error": "Missing metadata from map generation"}
    
    variable = date_info.get("variable")
    date_str = date_info.get("date_str")
    region = date_info.get("region", "unknown")
    
    if not variable or not date_str:
        logging.error(f"❌ Incomplete metadata: variable={variable}, date={date_str}")
        return {"error": f"Incomplete metadata"}
    
    logging.info(f"✅ Using metadata: variable={variable}, date={date_str}, region={region}")
    
    # Get bounds
    bounds = map_data.get("bounds", {})
    if not bounds or not all(k in bounds for k in ["north", "south", "east", "west"]):
        logging.error(f"❌ Invalid bounds: {bounds}")
        return {"error": "Invalid geographic bounds"}
    
    north = float(bounds["north"])
    south = float(bounds["south"])
    east = float(bounds["east"])
    west = float(bounds["west"])
    
    logging.info(f"🗺️ Bounds: N={north:.4f}, S={south:.4f}, E={east:.4f}, W={west:.4f}")
    
    # Check for pre-computed data
    metadata = map_data.get("metadata", {})
    computation_type = metadata.get("computation_type", "raw")
    computed_data_url = metadata.get("computed_data_url")
    computed_data_hash = metadata.get("computed_data_hash")
    
    if computed_data_url and computed_data_hash and computation_type != "raw":
        # Use pre-computed data
        logging.info(f"✅ Using pre-computed data: {computation_type}")
        
        color_scale = metadata.get("color_scale", {})
        vmin = color_scale.get("vmin")
        vmax = color_scale.get("vmax")
        cmap = color_scale.get("cmap", "viridis")
        
        if vmin is None or vmax is None:
            logging.error(f"❌ Missing color scale")
            return {"error": "Missing color scale for computed data"}
        
        zoom = determine_optimal_zoom_level(bounds)
        nw_tile = mercantile.tile(west, north, zoom)
        se_tile = mercantile.tile(east, south, zoom)
        
        tile_list = []
        for x in range(nw_tile.x, se_tile.x + 1):
            for y in range(nw_tile.y, se_tile.y + 1):
                tile_bounds = mercantile.bounds(mercantile.Tile(x, y, zoom))
                tile_list.append({
                    "z": zoom,
                    "x": x,
                    "y": y,
                    "url": f"http://localhost:8000/api/tiles/computed/{computed_data_hash}/{zoom}/{x}/{y}.png?vmin={vmin}&vmax={vmax}&cmap={cmap}",
                    "bounds": {
                        "north": tile_bounds.north,
                        "south": tile_bounds.south,
                        "east": tile_bounds.east,
                        "west": tile_bounds.west
                    }
                })
        
        return {
            "tile_url": f"http://localhost:8000/api/tiles/computed/{computed_data_hash}/{{z}}/{{x}}/{{y}}.png?vmin={vmin}&vmax={vmax}&cmap={cmap}",
            "variable": variable,
            "date": date_str,
            "computation_type": computation_type,
            "zoom": zoom,
            "tile_list": tile_list,
            "region_bounds": {"north": north, "south": south, "east": east, "west": west},
            "uses_precomputed_data": True
        }
    
    else:
        # Raw data tiles
        logging.info(f"✅ Using raw data tiles")
        
        date_parts = date_str.split('-')
        year = int(date_parts[0])
        month = int(date_parts[1])
        day = int(date_parts[2]) if len(date_parts) > 2 else None
        
        # Calculate data range
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
                if hasattr(data, 'squeeze'):
                    data = data.squeeze()
                region_vmin, region_vmax = -2.5, 2.5
            else:
                ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
                data = ds[variable].sel(
                    lat=builtins.slice(south, north),
                    lon=builtins.slice(west, east)
                )
                
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
            logging.info(f"🎨 Calculated scale: {region_vmin:.2f} to {region_vmax:.2f}")
            
        except Exception as e:
            logging.error(f"❌ Failed to calculate scale: {e}")
            if variable == 'SPI3':
                region_vmin, region_vmax = -2.5, 2.5
            elif variable == 'Tair':
                region_vmin, region_vmax = -10, 30
            elif variable == 'Rainf':
                region_vmin, region_vmax = 0, 50
            else:
                region_vmin, region_vmax = 0, 100
        
        zoom = determine_optimal_zoom_level(bounds)
        nw_tile = mercantile.tile(west, north, zoom)
        se_tile = mercantile.tile(east, south, zoom)
        
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
        
        return {
            "tile_url": f"http://localhost:8000/api/tiles/{variable}/{date_str}/{{z}}/{{x}}/{{y}}.png?vmin={region_vmin}&vmax={region_vmax}",
            "variable": variable,
            "date": date_str,
            "zoom": zoom,
            "tile_list": tile_list,
            "region_bounds": {"north": north, "south": south, "east": east, "west": west},
            "uses_precomputed_data": False
        }


def normalize_map_result_dict(raw: dict, original_query: str) -> dict:
    """Guarantee required keys for map dict"""
    static_url = raw.get("static_url")
    overlay_url = raw.get("overlay_url") or raw.get("transparent_url")
    
    if overlay_url is None and static_url:
        overlay_url = static_url
    if static_url is None and overlay_url:
        static_url = overlay_url
    
    geojson = raw.get("geojson") or {"type":"FeatureCollection","features":[]}
    bounds = raw.get("bounds") or {}
    
    center = [
        float((bounds.get("east", -98) + bounds.get("west", -98)) / 2),
        float((bounds.get("north", 39) + bounds.get("south", 39)) / 2)
    ]
    
    map_config = raw.get("map_config") or {
        "center": center,
        "zoom": 6,
        "style": "satellite",
        "overlay_mode": True
    }
    
    if "center" not in map_config or not map_config["center"]:
        map_config["center"] = center
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


def should_use_tiles(user_query: str, map_data: dict) -> bool:
    """Always use tiles - unified approach"""
    bounds = map_data.get("bounds", {})
    if not bounds:
        logging.warning("❌ No bounds - cannot use tiles")
        return False
    
    logging.info("✅ Using tiles (unified approach)")
    return True


def extract_agent_text_response(thread_id: str) -> str:
    """Extract the most recent assistant message"""
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
        
        return "Hello! I'm the NLDAS-3 Weather Assistant. How can I help you today?"
        
    except Exception as e:
        logging.error(f"❌ Error extracting text: {e}", exc_info=True)
        return "Hello! I'm here to help with weather data."


def extract_analysis_info(query: str, result: dict, memory_context: dict = None) -> dict:
    """
    Extract variable, region, and date from result metadata, query, or memory
    
    Priority:
    1. Result metadata (most reliable)
    2. Query parsing
    3. Memory context
    """
    import re
    
    query_lower = query.lower()
    
    # PRIORITY 1: Result metadata
    variable = None
    date_str = None
    region = "unknown"
    
    if result and "metadata" in result:
        metadata = result["metadata"]
        variable = metadata.get("variable")
        date_str = metadata.get("date")
        region = metadata.get("region", "unknown")
        
        if variable:
            logging.info(f"✅ Metadata: variable={variable}, date={date_str}, region={region}")
            return {
                "variable": variable,
                "region": region,
                "date_str": date_str
            }
    
    # Fallback: color_scale
    if not variable and result:
        color_scale = result.get("color_scale", {})
        if color_scale and "variable" in color_scale:
            variable = color_scale["variable"]
            logging.info(f"📊 From color_scale: {variable}")
    
    # PRIORITY 2: Check memory for "same" queries
    if not variable and memory_context and any(word in query_lower for word in ['same', 'similar', 'that', 'this']):
        mem_metadata = memory_context.get('metadata', {})
        if mem_metadata.get('last_variable'):
            variable = mem_metadata['last_variable']
            logging.info(f"📝 From memory: {variable}")
    
    # PRIORITY 3: Parse query
    if not variable:
        if any(word in query_lower for word in ['drought', 'spi']):
            variable = "SPI3"
        elif any(word in query_lower for word in ['precipitation', 'rain', 'rainfall', 'precip']):
            variable = "Rainf"
        elif any(word in query_lower for word in ['temperature', 'temp']):
            variable = "Tair"
    
    if not variable:
        logging.error(f"❌ Could not detect variable: {query}")
        return {"error": "Could not determine weather variable"}
    
    # Extract region
    if region == "unknown":
        if memory_context:
            mem_metadata = memory_context.get('metadata', {})
            if mem_metadata.get('last_region'):
                region = mem_metadata['last_region']
        
        if region == "unknown":
            regions = {
                'michigan': 'michigan', 'florida': 'florida', 'california': 'california',
                'maryland': 'maryland', 'texas': 'texas', 'alaska': 'alaska',
                'hope': 'alaska', 'southeast': 'southeast'
            }
            for key, value in regions.items():
                if key in query_lower:
                    region = value
                    break
    
    # Extract date
    if not date_str:
        if memory_context and any(word in query_lower for word in ['same', 'similar', 'that', 'this']):
            mem_metadata = memory_context.get('metadata', {})
            if mem_metadata.get('last_date'):
                date_str = mem_metadata['last_date']
                logging.info(f"📅 Date from memory: {date_str}")
        
        if not date_str:
            year_match = re.search(r'(20\d{2})', query)
            year = int(year_match.group(1)) if year_match else 2023
            
            month_names = ['january','february','march','april','may','june',
                          'july','august','september','october','november','december']
            month_match = re.search(r'(' + '|'.join(month_names) + ')', query_lower)
            month = month_names.index(month_match.group(1)) + 1 if month_match else 6
            
            if variable != "SPI3":
                day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', query)
                day = int(day_match.group(1)) if day_match else 15
            
            if variable == "SPI3":
                date_str = f"{year}-{month:02d}"
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
    
    logging.info(f"📊 Final: variable={variable}, region={region}, date={date_str}")
    
    return {
        "variable": variable,
        "region": region,
        "date_str": date_str
    }


def handle_chat_request(data):
    """
    Handle chat requests with PROPER memory integration
    """
    start_total = time.time()
    times = {}
    
    try:
        # ===== VALIDATION =====
        t1 = time.time()
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        logging.info(f"\n{'='*80}")
        logging.info(f"🆕 NEW REQUEST: {user_query}")
        logging.info(f"{'='*80}")
        
        # Get user_id
        user_id = data.get("user_id", f"anonymous_{hash(user_query) % 10000}")
        logging.info(f"👤 User ID: {user_id}")
        
        # ⚠️ CRITICAL WARNING for anonymous users
        if user_id.startswith("anonymous_"):
            logging.warning(f"⚠️ ANONYMOUS USER: {user_id}")
            logging.warning("   Memory will NOT persist across sessions!")
            logging.warning("   Pass a real user_id in the request to enable memory")
        
        times['validation'] = time.time() - t1
        
        # ===== MEMORY RETRIEVAL =====
        t2 = time.time()
        
        # Check total memories for this user
        all_user_memories = memory_manager.get_all(user_id)
        memory_count = len(all_user_memories) if isinstance(all_user_memories, list) else len(all_user_memories.get('results', []))
        logging.info(f"📊 User {user_id[:8]}... has {memory_count} total memories")
        
        # Retrieve recent and relevant memories
        recent_memories = memory_manager.recent_context(user_id, limit=3)
        relevant_memories = memory_manager.search(user_query, user_id, limit=3)
        
        logging.info(f"📚 Recent memories: {len(recent_memories)}")
        logging.info(f"🔍 Relevant memories: {len(relevant_memories)}")
        
        # Build structured memory context
        memory_context = build_structured_memory_context(recent_memories, relevant_memories, user_id)
        
        # Construct enhanced query with explicit memory instructions
        enhanced_query = construct_enhanced_query(user_query, memory_context)
        
        # Log what we're sending to the agent
        logging.info(f"\n{'='*80}")
        logging.info(f"📤 SENDING TO AGENT:")
        logging.info(f"{'='*80}")
        logging.info(f"Has memory: {memory_context['metadata']['has_memory']}")
        if memory_context['metadata']['has_memory']:
            logging.info(f"Last variable: {memory_context['metadata']['last_variable']}")
            logging.info(f"Last region: {memory_context['metadata']['last_region']}")
            logging.info(f"Last date: {memory_context['metadata']['last_date']}")
        logging.info(f"\nQuery preview:\n{enhanced_query[:500]}...")
        logging.info(f"{'='*80}\n")
        
        times['memory_retrieval'] = time.time() - t2
        
        # ===== THREAD MANAGEMENT =====
        t3 = time.time()
        thread_id = data.get("thread_id")
        
        if thread_id:
            try:
                thread = project_client.agents.threads.retrieve(thread_id=thread_id)
                logging.info(f"♻️ Reusing thread: {thread.id}")
            except Exception as e:
                logging.warning(f"⚠️ Thread {thread_id} invalid: {e}")
                thread = project_client.agents.threads.create()
                logging.info(f"🆕 Created new thread: {thread.id}")
        else:
            thread = project_client.agents.threads.create()
            logging.info(f"🆕 Created thread: {thread.id}")
        
        times['thread_creation'] = time.time() - t3
        
        # ===== MESSAGE CREATION =====
        t4 = time.time()
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=enhanced_query
        )
        logging.info(f"✉️ Created message: {message.id}")
        times['message_creation'] = time.time() - t4
        
        # ===== RUN CREATION =====
        t5 = time.time()
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        logging.info(f"🚀 Started run: {run.id}")
        times['run_creation'] = time.time() - t5
        
        # ===== ANALYSIS DETECTION =====
        analysis_keywords = [
            'most significant', 'most extreme', 'hottest', 'coldest',
            'warmest', 'wettest', 'driest', 'highest', 'lowest',
            'top', 'worst', 'best', 'find', 'where are'
        ]
        is_analysis_query = any(phrase in user_query.lower() for phrase in analysis_keywords)
        
        if is_analysis_query:
            logging.info(f"🔍 Detected analysis query - using direct function")
            try:
                from .dynamic_code_generator import analyze_extreme_regions
                analysis_result = analyze_extreme_regions(user_query)
                
                if analysis_result.get("status") == "success":
                    result_value = analysis_result.get("result")
                    
                    # Store in memory
                    memory_manager.add(
                        f"Query: {user_query}\nAnalysis: Found {len(result_value.get('regions', []))} extreme regions",
                        user_id,
                        {"type": "analysis", "query": user_query}
                    )
                    
                    times['total'] = time.time() - start_total
                    
                    return make_json_serializable({
                        "status": "success",
                        "content": f"Analysis completed: Found {len(result_value.get('regions', []))} extreme regions",
                        "analysis_data": analysis_result,
                        "type": "analysis_complete",
                        "regions": result_value.get("regions", []),
                        "geojson": result_value.get("geojson", {}),
                        "bounds": result_value.get("bounds", {}),
                        "temperature_data": build_temperature_data(result_value.get("geojson", {})),
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "user_id": user_id,
                        "timing_breakdown": times
                    })
            except Exception as e:
                logging.error(f"❌ Direct analysis failed: {e}")
        
        # ===== EXECUTION LOOP =====
        t8 = time.time()
        max_iterations = 20
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        
        start_time = time.time()
        max_total_time = 120
        max_in_progress_time = 8
        last_status_change = start_time
        
        while iteration < max_iterations:
            iteration += 1
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            logging.info(f"🔄 Status: {run.status} (iter {iteration}/{max_iterations}, {elapsed_time:.1f}s)")
            
            if elapsed_time > max_total_time:
                logging.warning(f"⏰ TIMEOUT: {max_total_time}s exceeded")
                break
            
            # Stuck detection
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
                            content="EXECUTE NOW! Call execute_custom_code immediately."
                        )
                        
                        run = project_client.agents.runs.create(
                            thread_id=thread.id,
                            agent_id=text_agent_id
                        )
                        
                        last_status_change = time.time()
                        logging.info("🔄 Restarted run")
                    except Exception as e:
                        logging.error(f"❌ Failed to restart: {e}")
                        break
            
            # ===== COMPLETED =====
            if run.status == "completed":
                logging.info("✅ Run completed")
                
                if not custom_code_executed:
                    text_response = extract_agent_text_response(thread.id)
                    
                    # Store text response
                    memory_manager.add(
                        f"Query: {user_query}\nResponse: {text_response}",
                        user_id,
                        {"type": "conversation", "query": user_query}
                    )
                    logging.info(f"💾 Stored conversation for {user_id}")
                    
                    times['execution_loop'] = time.time() - t8
                    times['total'] = time.time() - start_total
                    
                    logging.info(f"⏱️ TIMING: {json.dumps(times, indent=2)}")
                    
                    return make_json_serializable({
                        "status": "success",
                        "content": text_response,
                        "type": "text_response",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "user_id": user_id,
                        "timing_breakdown": times
                    })
                else:
                    times['execution_loop'] = time.time() - t8
                    times['total'] = time.time() - start_total
                    
                    return make_json_serializable({
                        "status": "success",
                        "content": "Analysis completed",
                        "type": "code_execution_complete",
                        "analysis_data": analysis_data,
                        "thread_id": thread.id,
                        "user_id": user_id,
                        "timing_breakdown": times
                    })
            
            # ===== REQUIRES_ACTION =====
            elif run.status == "requires_action":
                logging.info("🛠️ Processing tool calls")
                
                if run.required_action and run.required_action.submit_tool_outputs:
                    tool_calls = run.required_action.submit_tool_outputs.tool_calls
                    logging.info(f"🔧 {len(tool_calls)} tool call(s)")
                    
                    tool_outputs = []
                    
                    for tool_call in tool_calls:
                        if tool_call.function.name == "execute_custom_code":
                            try:
                                raw_arguments = tool_call.function.arguments
                                
                                if not raw_arguments or not raw_arguments.strip():
                                    function_args = {
                                        "python_code": "result = 'Hello! I can help with weather data.'",
                                        "user_request": user_query
                                    }
                                else:
                                    function_args = json.loads(raw_arguments)
                                
                                function_args["user_id"] = user_id
                                
                                logging.info("🚀 Executing custom code...")
                                analysis_result = execute_custom_code(function_args)
                                custom_code_executed = True
                                analysis_data = analysis_result
                                
                                if analysis_result.get("status") == "success":
                                    result_value = analysis_result.get("result")
                                    
                                    # Handle map results
                                    if isinstance(result_value, dict) and ("static_url" in result_value or "overlay_url" in result_value):
                                        logging.info("🗺️ Map result detected")
                                        
                                        # Extract info (passing memory_context)
                                        extracted_info = extract_analysis_info(user_query, result_value, memory_context)
                                        
                                        # Store if extraction succeeded
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
                                            logging.info(f"💾 Stored analysis memory for {user_id}")
                                        else:
                                            logging.warning(f"⚠️ Skipping memory: {extracted_info.get('error')}")
                                        
                                        # Continue processing
                                        enriched = normalize_map_result_dict(result_value, user_query)
                                        enriched["temperature_data"] = build_temperature_data(enriched.get("geojson", {}))
                                        
                                        use_tiles = should_use_tiles(user_query, enriched)
                                        
                                        if use_tiles:
                                            if "error" not in extracted_info:
                                                tile_config = create_tile_config(enriched, user_query, extracted_info)
                                            else:
                                                tile_config = create_tile_config(enriched, user_query, date_info=None)
                                            
                                            if "error" in tile_config:
                                                logging.warning(f"⚠️ Tile error: {tile_config['error']}")
                                                
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
                                                
                                                return make_json_serializable({
                                                    "status": "success",
                                                    "content": enriched.get("static_url", "Map generated"),
                                                    "static_url": enriched.get("static_url"),
                                                    "overlay_url": enriched.get("overlay_url"),
                                                    "geojson": enriched["geojson"],
                                                    "bounds": enriched["bounds"],
                                                    "temperature_data": enriched["temperature_data"],
                                                    "type": "visualization_with_overlay",
                                                    "thread_id": thread.id,
                                                    "user_id": user_id,
                                                    "tile_error": tile_config.get('error'),
                                                    "timing_breakdown": times
                                                })
                                            
                                            # Success
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
                                            
                                            return make_json_serializable({
                                                "status": "success",
                                                "content": "Interactive map generated",
                                                "use_tiles": True,
                                                "tile_config": tile_config,
                                                "static_url": enriched.get("static_url"),
                                                "geojson": enriched["geojson"],
                                                "bounds": enriched["bounds"],
                                                "temperature_data": enriched["temperature_data"],
                                                "type": "visualization_with_tiles",
                                                "thread_id": thread.id,
                                                "user_id": user_id,
                                                "timing_breakdown": times
                                            })
                                        
                                        else:
                                            # Static only
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
                                            
                                            return make_json_serializable({
                                                "status": "success",
                                                "content": enriched.get("static_url", "Map generated"),
                                                "static_url": enriched.get("static_url"),
                                                "overlay_url": enriched.get("overlay_url"),
                                                "geojson": enriched["geojson"],
                                                "bounds": enriched["bounds"],
                                                "temperature_data": enriched["temperature_data"],
                                                "type": "visualization_with_overlay",
                                                "thread_id": thread.id,
                                                "user_id": user_id,
                                                "timing_breakdown": times
                                            })
                                    else:
                                        # Text result
                                        memory_manager.add(
                                            f"Query: {user_query}\nResult: {str(result_value)[:200]}",
                                            user_id,
                                            {"type": "analysis", "query": user_query}
                                        )
                                        
                                        tool_outputs.append({
                                            "tool_call_id": tool_call.id,
                                            "output": json.dumps({"status": "success", "result": str(result_value)})
                                        })
                                else:
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
                    
                    # Submit outputs
                    try:
                        project_client.agents.runs.submit_tool_outputs(
                            thread_id=thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                        logging.info("✅ Submitted tool outputs")
                    except Exception as e:
                        logging.error(f"❌ Submit failed: {e}")
            
            # ===== FAILED/CANCELLED/EXPIRED =====
            elif run.status in ["failed", "cancelled", "expired"]:
                logging.error(f"❌ Run {run.status}")
                times['execution_loop'] = time.time() - t8
                times['total'] = time.time() - start_total
                
                return make_json_serializable({
                    "status": "error",
                    "content": f"Agent run {run.status}",
                    "type": f"run_{run.status}",
                    "thread_id": thread.id,
                    "user_id": user_id,
                    "timing_breakdown": times
                })
            
            # ===== QUEUED/IN_PROGRESS =====
            elif run.status in ["queued", "in_progress"]:
                time.sleep(0.5 if run.status == "in_progress" else 0.3)
            
            # Refresh
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"❌ Refresh error: {e}")
                break
        
        # Timeout
        times['execution_loop'] = time.time() - t8
        times['total'] = time.time() - start_total
        
        logging.error(f"❌ Timeout after {iteration} iterations")
        
        return make_json_serializable({
            "status": "timeout_failure",
            "content": f"Timeout after {iteration} iterations",
            "type": "timeout",
            "thread_id": thread.id,
            "user_id": user_id,
            "timing_breakdown": times
        })
        
    except Exception as e:
        times['total'] = time.time() - start_total
        logging.error(f"❌ Error: {e}", exc_info=True)
        
        return make_json_serializable({
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__,
            "user_id": data.get("user_id", "unknown"),
            "thread_id": data.get("thread_id"),
            "timing_breakdown": times
        })


def make_json_serializable(obj, _seen=None):
    """Enhanced JSON serialization"""
    import types
    from datetime import datetime, date
    
    if _seen is None:
        _seen = set()
    
    obj_id = id(obj)
    if obj_id in _seen:
        return f"<circular reference to {type(obj).__name__}>"
    
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    
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
            try:
                return {k: make_json_serializable(v, _seen) for k, v in obj.__dict__.items() if not k.startswith('_')}
            except:
                return str(obj)
        elif hasattr(obj, '_asdict'):
            return make_json_serializable(obj._asdict(), _seen)
        else:
            return str(obj)
    except Exception:
        return f"<serialization error: {type(obj).__name__}>"
    finally:
        _seen.discard(obj_id)