# agents/agent_chat.py - Fixed version with better timeout and error handling
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
import re
import hashlib  # Add this import at top
from .dynamic_code_generator import execute_custom_code
from .dataset_metadata import build_coverage_response
from .memory_manager import memory_manager  # Add this import

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
    ULTRA-DIRECT: Immediate function execution with Azure Maps detection + Memory Integration
    """
    try:
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        
        # CRITICAL: Extract stable user ID for memory
        user_id = get_user_id(data.get('_request'), data)  # Pass request if available
        logging.info(f"🆔 Processing request for user: {user_id[:8]}...")
        
        # STEP 1: Search for relevant memories BEFORE processing
        memory_context = []
        if memory_manager.enabled and user_id != 'anonymous':
            try:
                memories = memory_manager.search(user_query, user_id=user_id, limit=3)
                memory_context = [mem.get('memory', '') for mem in memories if mem.get('memory')]
                if memory_context:
                    logging.info(f"🧠 Found {len(memory_context)} relevant memories for context")
                else:
                    logging.info("🧠 No relevant memories found")
            except Exception as mem_error:
                logging.warning(f"Memory search failed: {mem_error}")

        logging.info(f"Processing chat request: {user_query}")

        # Coverage query check (unchanged)
        if is_coverage_query(user_query):
            logging.info("Detected coverage / availability query; returning metadata without tool execution.")
            coverage = build_coverage_response()
            return {
                "status": "coverage_info",
                "content": coverage["summary"],
                "coverage": coverage,
                "agent_id": text_agent_id
            }

        # Heuristic signals (unchanged)
        q_lower = user_query.lower()
        has_var = any(k in q_lower for k in ["temperature","tair","precip","rain","rainf","humidity","qair","spi","drought","wind","pressure","psurf"])
        has_place = any(k in q_lower for k in ["florida","alaska","california","michigan","texas","ohio","virginia","colorado","arizona","georgia","maryland","nevada","oregon","washington"])
        has_date_token = any(tok in q_lower for tok in [" 2020"," 2021"," 2022"," 2023"," jan"," feb"," mar"," apr"," may"," jun"," jul"," aug"," sep"," oct"," nov"," dec"])
        minimal_context = not (has_var and (has_place or has_date_token))

        # Create thread
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")

        # ENHANCED PROMPT: Include memory context and better conversation handling
        memory_context_text = ""
        if memory_context:
            memory_context_text = f"\n\nRELEVANT CONVERSATION HISTORY:\n"
            for i, mem in enumerate(memory_context, 1):
                memory_context_text += f"{i}. {mem}\n"
            memory_context_text += "\nUse this context to better understand the user's request.\n"

        enhanced_query = f"""You are an NLDAS-3 hydrometeorological assistant with memory of previous conversations.

USER QUERY: "{user_query}"{memory_context_text}

DECISION RULES:
1. If user asks about "apple maps" or non-weather topics -> Politely redirect to weather data and ask for variable + location + date.
2. If user provides missing information from previous conversation -> Use the memory context to complete the request.
3. If query lacks required info (variable, location, OR date) -> Ask specifically for what's missing.
4. ONLY call execute_custom_code when you have: variable + location + date/timeframe.
5. When calling execute_custom_code, provide complete JSON with python_code and user_request.

MEMORY-AWARE PROCESSING:
- If memory shows previous incomplete requests, try to fill gaps with current query
- If user says "temperature" and "maryland" after asking about maps, combine this information
- Remember user preferences for future interactions

ACTIONABILITY ASSESSMENT:
- variable_detected: {has_var}  
- location_detected: {has_place}
- date_token_detected: {has_date_token}
- minimal_context: {minimal_context}
- memory_context_available: {len(memory_context) > 0}

Examples of good memory integration:
- Previous: "show me maps" → Current: "temperature for maryland" → Generate temperature map for Maryland
- Previous: "drought data for May 2023" → Current: "same for California" → Generate drought data for California in May 2023

Respond now following the rules above."""

        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user", 
            content=enhanced_query
        )
        logging.info(f"Created message: {message.id}")

        # Start run (unchanged process)
        run = project_client.agents.runs.create(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        logging.info(f"Started run: {run.id}")

        # MEMORY INTEGRATION: Store the conversation
        if memory_manager.enabled and user_id != 'anonymous':
            try:
                # Store user query in memory for future reference
                memory_manager.add(
                    f"User query: {user_query}",
                    user_id=user_id,
                    meta={"type": "user_query", "timestamp": time.time()}
                )
            except Exception as mem_error:
                logging.warning(f"Failed to store user query in memory: {mem_error}")

# ...existing code for run processing...

            # MEMORY INTEGRATION: In the success handling section, store the result
            if analysis_result.get("status") == "success":
                result_value = analysis_result.get("result", "No result")
                
                # Store successful analysis in memory
                if memory_manager.enabled and user_id != 'anonymous':
                    try:
                        if isinstance(result_value, str) and result_value.startswith("http"):
                            memory_manager.add(
                                f"Generated visualization for: {user_query}. Result: {result_value}",
                                user_id=user_id,
                                meta={"type": "successful_analysis", "result_type": "visualization"}
                            )
                        else:
                            memory_manager.add(
                                f"Analysis completed for: {user_query}. Result: {str(result_value)[:100]}...",
                                user_id=user_id,
                                meta={"type": "successful_analysis", "result_type": "data"}
                            )
                    except Exception as mem_error:
                        logging.warning(f"Failed to store result in memory: {mem_error}")

# ...existing code continues unchanged...