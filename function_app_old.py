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

# Explicit root route to discourage scanners 
@app.route(route="", auth_level=func.AuthLevel.ANONYMOUS)
def root(req: func.HttpRequest) -> func.HttpResponse:  # renamed '_' -> 'req' to satisfy binding
    path = req.route_params.get('*', '/')  # defensive
    ua = req.headers.get("User-Agent", "")
    lower_path = path.lower()
    # Simple probe heuristics
    suspicious = any(p in lower_path for p in [
        "cgi-bin", ".php", ".aspx", ".cfm", "/scripts", "/ws202", "/magento", "default.aspx"
    ]) or ("msie" in ua.lower() or "trident" in ua.lower())
    if suspicious:
        # Minimal logging to reduce noise
        logging.debug(f"Blocked probe path={path} ua={ua}")
        return func.HttpResponse(status_code=404)
    return func.HttpResponse(
        json.dumps({
            "error": "No root resource.",
            "usage": "POST /multi_agent_function or /weather_query"
        }),
        status_code=404,
        mimetype="application/json"
    )

@app.route(route="nldas3_function", auth_level=func.AuthLevel.ANONYMOUS)
def nldas3_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Hello, {name}. This HTTP triggered function executed successfully.")
    else:
        return func.HttpResponse(
             "Error: Please provide a 'name' parameter in the query string or request body.",
             status_code=400
        )

@app.route(route="multi_agent_function", auth_level=func.AuthLevel.ANONYMOUS)
def multi_agent_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Multi-Agent HTTP trigger function processed a request.')

    try:
        # Parse the request body
        req_body = req.get_json()
        logging.info(f"Request body: {req_body}")

        action = req_body.get("action")  # e.g., "generate" or "visualize"
        data = req_body.get("data")  # Additional data for the agents
        logging.info(f"Action: {action}, Data: {data}")

        # Validate the action parameter
        if not action:
            return func.HttpResponse(
                json.dumps({"error": "Missing 'action' parameter"}),
                status_code=400,
                mimetype="application/json"
            )

        # Route the request based on the action
        if action == "generate":
            logging.info("Calling handle_chat_request...")
            response = handle_chat_request(data)
            logging.info(f"Response from handle_chat_request: {response}")
        elif action == "visualize":
            logging.info("Calling handle_visualization_request...")
            response = handle_visualization_request(data)
            logging.info(f"Response from handle_visualization_request: {response}")
        else:
            return func.HttpResponse(
                json.dumps({"error": f"Unknown action: {action}"}),
                status_code=400,
                mimetype="application/json"
            )

        # Return the agent's response
        return func.HttpResponse(
            json.dumps({"action": action, "response": response}),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error processing multi-agent request: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

@app.route(route="weather_query", auth_level=func.AuthLevel.ANONYMOUS)
def weather_query(req: func.HttpRequest) -> func.HttpResponse:
    """
    Direct weather data endpoint - now uses agent for parsing
    """
    logging.info('Weather query function processed a request.')
    
    try:
        # Get query parameters
        query = req.params.get('query')
        if not query:
            req_body = req.get_json()
            if req_body:
                query = req_body.get('query')
        
        if not query:
            return func.HttpResponse(
                json.dumps({"error": "Please provide a 'query' parameter"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Use the agent to parse and handle the query instead of hardcoded parsing
        logging.info(f"Sending query to agent: {query}")
        result = handle_chat_request({"query": query})
        
        return func.HttpResponse(
            json.dumps({
                "query": query,
                "result": result,
                "parsed_by": "gpt-4o-agent"
            }),
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Weather query error: {e}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )