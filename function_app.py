# function_app.py - Fixed version without signal timeout (Azure Functions doesn't support signals)
import azure.functions as func
import logging
import json
import sys
import os
import traceback
from datetime import datetime
import numpy as np

# Configure logging first
logging.basicConfig(level=logging.INFO)
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

# Import your agent modules with error handling
try:
    import os
    import tempfile
    
    # Log current working directory and temp directory
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Temp directory: {tempfile.gettempdir()}")
    logger.info(f"Python path: {sys.path[:3]}")  # First 3 entries only
    
    # Fix the import issue
    from agents.agent_chat import handle_chat_request
    logger.info("✅ handle_chat_request imported successfully")
    
    # Import other modules
    try:
        from agents.agent_visualization import handle_visualization_request
        logger.info("✅ handle_visualization_request imported successfully")
    except ImportError as viz_error:
        logger.warning(f"⚠️ Could not import visualization handler: {viz_error}")
    
    try:
        from agents.weather_tool import handle_weather_function_call
        logger.info("✅ handle_weather_function_call imported successfully")
    except ImportError as weather_error:
        logger.warning(f"⚠️ Could not import weather handler: {weather_error}")
    
    logger.info("✅ Core agent modules imported successfully")
    
    # Set flag for successful import
    AGENTS_IMPORTED = True
    IMPORT_ERROR_MSG = None
    
except Exception as import_error:
    logger.error(f"❌ CRITICAL: Failed to import agent modules: {import_error}")
    logger.error(f"❌ Traceback: {traceback.format_exc()}")
    
    # Set flag for failed import
    AGENTS_IMPORTED = False
    IMPORT_ERROR_MSG = str(import_error)
    
    # Define a fallback function using the captured error message
    def handle_chat_request(data):
        return {
            "status": "error",
            "content": f"Agent modules not available: {IMPORT_ERROR_MSG}",
            "error_type": "ImportError"
        }

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="multi_agent_function", auth_level=func.AuthLevel.ANONYMOUS)
def multi_agent_function(req: func.HttpRequest) -> func.HttpResponse:
    logger.info('🚀 NLDAS-3 weather analysis request received.')

    try:
        # Parse the request body with better error handling
        try:
            req_body = req.get_json()
            if not req_body:
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
            return func.HttpResponse(
                safe_json_dumps({"error": "No query or input provided"}),
                status_code=400,
                mimetype="application/json"
            )

        # Check if agents were imported successfully
        if not AGENTS_IMPORTED:
            return func.HttpResponse(
                safe_json_dumps({
                    "error": f"Agent modules failed to import: {IMPORT_ERROR_MSG}",
                    "error_type": "ImportError",
                    "status": "initialization_error"
                }),
                status_code=503,
                mimetype="application/json"
            )

        # Route to generate with enhanced error handling
        try:
            response = handle_chat_request(data)
            logger.info(f"✅ Request processed successfully. Response type: {type(response)}")
            
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
                    "error_type": type(chat_error).__name__
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
                "message": "Function completed with error but did not crash"
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
            "timestamp": str(datetime.utcnow())
        }),
        status_code=200,
        mimetype="application/json"
    )