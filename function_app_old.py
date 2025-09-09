import azure.functions as func
import logging
import json
import sys
import os

# Add the project root to PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import your agent modules
from agents.agent_chat import handle_chat_request  # Ensure this is correctly imported
from agents.agent_visualization import handle_visualization_request

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

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














