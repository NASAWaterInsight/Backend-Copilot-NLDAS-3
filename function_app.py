# function_app.py - Updated with weather tool integration
import azure.functions as func
import logging
import json
import sys
import os

# Add the project root to PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import your agent modules and weather tool
from agents.agent_chat import handle_chat_request
from agents.agent_visualization import handle_visualization_request
from agents.weather_tool import handle_weather_function_call

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="multi_agent_function", auth_level=func.AuthLevel.ANONYMOUS)
def multi_agent_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('NLDAS-3 weather analysis request processed.')

    try:
        # Parse the request body
        req_body = req.get_json()
        
        # Support both "action/data" format and direct "query" format
        if "action" in req_body:
            data = req_body.get("data", {})
        else:
            # Direct query format: {"query": "show me temperature..."}
            data = req_body

        logging.info(f"Processing request: {data}")

        # Always route to generate (handles both text and visualizations)
        response = handle_chat_request(data)
        
        return func.HttpResponse(
            json.dumps({"response": response}),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error processing request: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )