# function_app.py - Enhanced version with better import debugging
import azure.functions as func
import logging
import json
import sys
import os
import traceback
from datetime import datetime
import numpy as np

# Configure logging first with more detailed output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the project root to PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Custom JSON encoder to handle numpy arrays and other non-serializable objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif hasattr(obj, 'isoformat'):  # datetime objects
            return obj.isoformat()
        else:
            # For any other non-serializable object, convert to string
            return str(obj)

def safe_json_dumps(obj):
    """Safely convert object to JSON string, handling numpy arrays and other types"""
    try:
        return json.dumps(obj, cls=CustomJSONEncoder, indent=None, separators=(',', ':'))
    except Exception as e:
        logger.warning(f"JSON serialization warning: {e}")
        # Fallback: convert problematic objects to strings
        return json.dumps({"error": f"Serialization issue: {str(e)}", "data": str(obj)})

# ENHANCED Import debugging
logger.info("🚀 Starting agent module import process...")
logger.info(f"📂 Current working directory: {os.getcwd()}")
logger.info(f"📂 File location: {__file__}")
logger.info(f"🐍 Python version: {sys.version}")
logger.info(f"📦 Python path entries: {len(sys.path)}")

# Check if agents directory exists
agents_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agents')
logger.info(f"👀 Checking agents directory: {agents_dir}")
logger.info(f"📁 Agents directory exists: {os.path.exists(agents_dir)}")

if os.path.exists(agents_dir):
    agents_files = os.listdir(agents_dir)
    logger.info(f"📋 Files in agents directory: {agents_files}")
else:
    logger.error("❌ CRITICAL: agents directory not found!")

# Import your agent modules with enhanced error handling
try:
    logger.info("🔄 Attempting to import agent modules...")
    
    # Test basic imports first
    try:
        import pandas as pd
        logger.info(f"✅ pandas {pd.__version__} imported")
    except ImportError as e:
        logger.error(f"❌ pandas import failed: {e}")
    
    try:
        import matplotlib
        matplotlib.use('Agg')
        logger.info(f"✅ matplotlib {matplotlib.__version__} configured with Agg backend")
    except ImportError as e:
        logger.error(f"❌ matplotlib import failed: {e}")
    
    # Now try agent imports with specific error tracking
    logger.info("🎯 Importing handle_chat_request...")
    from agents.agent_chat import handle_chat_request
    logger.info("✅ handle_chat_request imported successfully")
    
    # Import other modules with individual error handling
    try:
        logger.info("🎯 Importing handle_visualization_request...")
        #from agents.agent_visualization import handle_visualization_request
        logger.info("✅ handle_visualization_request imported successfully")
    except ImportError as viz_error:
        logger.warning(f"⚠️ Could not import visualization handler: {viz_error}")
        handle_visualization_request = None
    
    try:
        logger.info("🎯 Importing handle_weather_function_call...")
        from agents.weather_tool import handle_weather_function_call
        logger.info("✅ handle_weather_function_call imported successfully")
    except ImportError as weather_error:
        logger.warning(f"⚠️ Could not import weather handler: {weather_error}")
        handle_weather_function_call = None

    AZURE_MAPS_AVAILABLE = False  # unified workflow; flag no longer used
    azure_maps_detector = None
    
    logger.info("🎉 Core agent modules imported successfully")
    
    # Set flag for successful import
    AGENTS_IMPORTED = True
    IMPORT_ERROR_MSG = None
    
except Exception as import_error:
    logger.error(f"❌ CRITICAL: Failed to import agent modules")
    logger.error(f"❌ Import error: {import_error}")
    logger.error(f"❌ Import traceback: {traceback.format_exc()}")
    
    # Check specific import issues
    try:
        import sys
        logger.error(f"❌ Sys.path: {sys.path[:3]}")  # First 3 entries
    except:
        pass
    
    # Set flag for failed import
    AGENTS_IMPORTED = False
    IMPORT_ERROR_MSG = str(import_error)
    
    # Define a fallback function using the captured error message
    def handle_chat_request(data):
        return {
            "status": "initialization_error",
            "content": f"Agent modules failed to import: {IMPORT_ERROR_MSG}",
            "error_type": "ImportError",
            "debug": {
                "import_error": IMPORT_ERROR_MSG,
                "current_directory": os.getcwd(),
                "agents_directory_exists": os.path.exists(agents_dir) if 'agents_dir' in locals() else False
            }
        }

logger.info(f"📊 Import status: AGENTS_IMPORTED = {AGENTS_IMPORTED}")

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="multi_agent_function", auth_level=func.AuthLevel.ANONYMOUS)
def multi_agent_function(req: func.HttpRequest) -> func.HttpResponse:
    logger.info('🚀 NLDAS-3 weather analysis request received.')
    logger.info(f'📊 Agent import status: {AGENTS_IMPORTED}')

    try:
        # Parse the request body with better error handling
        try:
            req_body = req.get_json()
            if not req_body:
                logger.error("❌ No request body provided")
                return func.HttpResponse(
                    safe_json_dumps({"error": "No request body provided"}),
                    status_code=400,
                    mimetype="application/json"
                )
        except Exception as json_error:
            logger.error(f"❌ JSON parsing error: {json_error}")
            return func.HttpResponse(
                safe_json_dumps({"error": f"Invalid JSON: {str(json_error)}"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Support both "action/data" format and direct "query" format
        if "action" in req_body:
            data = req_body.get("data", {})
        else:
            # Direct query format: {"query": "show me temperature..."}
            data = req_body

        logger.info(f"📊 Processing request: {data}")

        # Add request validation
        if not data or (not data.get("query") and not data.get("input")):
            logger.error("❌ No query or input provided")
            return func.HttpResponse(
                safe_json_dumps({"error": "No query or input provided"}),
                status_code=400,
                mimetype="application/json"
            )

        # Enhanced agent import checking
        if not AGENTS_IMPORTED:
            logger.error(f"❌ Agents not imported: {IMPORT_ERROR_MSG}")
            return func.HttpResponse(
                safe_json_dumps({
                    "error": f"Agent modules failed to import: {IMPORT_ERROR_MSG}",
                    "error_type": "ImportError",
                    "status": "initialization_error",
                    "debug": {
                        "agents_imported": AGENTS_IMPORTED,
                        "import_error": IMPORT_ERROR_MSG,
                        "agents_directory": os.path.exists(agents_dir) if 'agents_dir' in locals() else "unknown"
                    }
                }),
                status_code=503,
                mimetype="application/json"
            )

        # Continue directly to unified chat handling
        user_query = data.get("query", data.get("input", ""))

        # Enhanced chat request handling
        try:
            logger.info("🎯 Calling handle_chat_request...")
            response = handle_chat_request(data)
            logger.info(f"✅ Request processed successfully. Response type: {type(response)}")
            
            # Log response status for debugging
            if isinstance(response, dict):
                response_status = response.get("status", "unknown")
                logger.info(f"📊 Response status: {response_status}")
            
            return func.HttpResponse(
                safe_json_dumps({"response": response}),
                status_code=200,
                mimetype="application/json"
            )
            
        except Exception as chat_error:
            logger.error(f"❌ Chat handler error: {chat_error}")
            logger.error(f"❌ Chat handler traceback: {traceback.format_exc()}")
            
            # Return error but don't crash
            return func.HttpResponse(
                safe_json_dumps({
                    "error": f"Chat processing failed: {str(chat_error)}",
                    "error_type": type(chat_error).__name__,
                    "traceback": traceback.format_exc()[-500:]  # Last 500 chars
                }),
                status_code=500,
                mimetype="application/json"
            )

    except Exception as e:
        logger.error(f"❌ TOP-LEVEL FUNCTION ERROR: {e}")
        logger.error(f"❌ TOP-LEVEL TRACEBACK: {traceback.format_exc()}")
        
        # Always return a response, never let the function crash
        return func.HttpResponse(
            safe_json_dumps({
                "error": f"System error: {str(e)}",
                "error_type": type(e).__name__,
                "message": "Function completed with error but did not crash",
                "traceback": traceback.format_exc()[-500:]
            }),
            status_code=500,
            mimetype="application/json"
        )

# Add a health check endpoint
@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        safe_json_dumps({
            "status": "healthy",
            "message": "NLDAS-3 function app is running",
            "timestamp": str(datetime.utcnow()),
            "agents_imported": AGENTS_IMPORTED,
            "import_error": IMPORT_ERROR_MSG if not AGENTS_IMPORTED else None
        }),
        status_code=200,
        mimetype="application/json"
    )

# Add a debug endpoint to help diagnose import issues
@app.route(route="debug", auth_level=func.AuthLevel.ANONYMOUS)
def debug_info(req: func.HttpRequest) -> func.HttpResponse:
    import os
    
    debug_info = {
        "agents_imported": AGENTS_IMPORTED,
        "import_error": IMPORT_ERROR_MSG,
        "current_directory": os.getcwd(),
        "file_location": __file__,
        "python_version": sys.version,
        "agents_directory_exists": os.path.exists(os.path.join(os.path.dirname(__file__), 'agents')),
        "sys_path_length": len(sys.path)
    }
    
    # Try to list agents directory
    try:
        agents_dir = os.path.join(os.path.dirname(__file__), 'agents')
        if os.path.exists(agents_dir):
            debug_info["agents_files"] = os.listdir(agents_dir)
        else:
            debug_info["agents_files"] = "Directory not found"
    except Exception as e:
        debug_info["agents_files"] = f"Error listing: {str(e)}"
    
    return func.HttpResponse(
        safe_json_dumps(debug_info),
        status_code=200,
        mimetype="application/json"
    )
@app.route(route="test_memory_detailed", auth_level=func.AuthLevel.ANONYMOUS)
def test_memory_detailed(req: func.HttpRequest) -> func.HttpResponse:
    """Force memory initialization and capture detailed error"""
    import traceback
    
    diagnostics = {
        "initialization_attempt": None,
        "error_details": None
    }
    
    try:
        # Force a fresh initialization attempt
        from agents.memory_manager import MemoryManager
        
        # Create a new instance to trigger initialization
        test_manager = MemoryManager()
        
        diagnostics["initialization_attempt"] = {
            "enabled": test_manager.enabled,
            "memory_exists": test_manager.memory is not None,
            "memory_type": str(type(test_manager.memory))
        }
        
        # If disabled, try manual initialization to catch the error
        if not test_manager.enabled:
            try:
                from mem0 import Memory
                
                # ✅ UPDATED CONFIG WITH LLM
                config = {
                    "llm": {
                        "provider": "azure_openai",
                        "config": {
                            "model": os.getenv("AZURE_OPENAI_MODEL", "gpt-4o"),
                            "temperature": 0.1,
                            "max_tokens": 1000,
                            "azure_kwargs": {
                                "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                                "azure_deployment": os.getenv("AZURE_OPENAI_MODEL", "gpt-4o"),
                                "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                                "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                            }
                        }
                    },
                    "vector_store": {
                        "provider": "azure_ai_search",
                        "config": {
                            "service_name": os.getenv("MEM0_SERVICE_NAME"),
                            "api_key": os.getenv("MEM0_API_KEY"),
                            "collection_name": os.getenv("MEM0_COLLECTION_NAME", "nldas_memories"),
                            "embedding_model_dims": int(os.getenv("MEM0_EMBED_DIMS", "1536")),
                        },
                    },
                    "embedder": {
                        "provider": "azure_openai",
                        "config": {
                            "model": os.getenv("MEM0_EMBED_MODEL", "text-embedding-ada-002"),
                            "embedding_dims": int(os.getenv("MEM0_EMBED_DIMS", "1536")),
                            "azure_kwargs": {
                                "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                                "azure_deployment": os.getenv("MEM0_EMBED_MODEL", "text-embedding-ada-002"),
                                "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                                "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                            },
                        },
                    },
                }
                
                # Try to create Memory object
                memory = Memory.from_config(config)
                diagnostics["initialization_attempt"]["manual_init"] = "SUCCESS"
                
            except Exception as init_error:
                diagnostics["error_details"] = {
                    "error_type": type(init_error).__name__,
                    "error_message": str(init_error),
                    "traceback": traceback.format_exc()
                }
        
    except Exception as e:
        diagnostics["error_details"] = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }
    
    return func.HttpResponse(
        safe_json_dumps(diagnostics),
        status_code=200,
        mimetype="application/json"
    )