import azure.functions as func
import logging
import json

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Testing Insomnia
@app.route(route="nldas3")
def nldas3_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('NLDAS-3 HTTP trigger function processed a request.')

    # Get parameters from the request
    parameter = req.params.get('parameter')  # precipitation, temperature, etc.
    location = req.params.get('location')
    date_range = req.params.get('date_range')
    
    # If not in query string, try to get from JSON body
    if not parameter or not location:
        try:
            req_body = req.get_json()
        except ValueError:
            req_body = None
        
        if req_body:
            parameter = parameter or req_body.get('parameter')
            location = location or req_body.get('location')
            date_range = date_range or req_body.get('date_range')

    # Set defaults if still missing
    parameter = parameter or 'precipitation'
    location = location or 'Maryland'
    date_range = date_range or '2024-01'

    # Process the NLDAS-3 data request
    if parameter == 'precipitation':
        result = f"NLDAS-3 precipitation data for {location} ({date_range}): Average 45mm/month from blob storage"
    elif parameter == 'temperature':
        result = f"NLDAS-3 temperature data for {location} ({date_range}): Average 23°C from blob storage"
    elif parameter == 'wind':
        result = f"NLDAS-3 wind data for {location} ({date_range}): Average 5.2 m/s from blob storage"
    else:
        result = f"NLDAS-3 {parameter} data for {location} ({date_range}): Data retrieved from blob storage and AI search"

    # Return JSON response
    return func.HttpResponse(
        json.dumps({
            "parameter": parameter,
            "location": location,
            "date_range": date_range,
            "result": result,
            "status": "success",
            "data_source": "NLDAS-3 blob storage with AI search integration"
        }),
        status_code=200,
        mimetype="application/json"
    )

# STEP 1: Queue trigger function (what the AI agent will call)
@app.queue_trigger(arg_name="msg", queue_name="azure-function-foo-input", connection="STORAGE_CONNECTION")
@app.queue_output(arg_name="outputQueue", queue_name="azure-function-foo-output", connection="STORAGE_CONNECTION")  
def queue_trigger(msg: func.QueueMessage, outputQueue: func.Out[str]):
    try:
        messagepayload = json.loads(msg.get_body().decode("utf-8"))
        logging.info(f'The function receives the following message: {json.dumps(messagepayload)}')
        
        # Extract NLDAS-3 specific parameters
        location = messagepayload.get("location", "Maryland")
        parameter = messagepayload.get("parameter", "precipitation")
        date_range = messagepayload.get("date_range", "2024-01")
        
        # Process NLDAS-3 data based on parameter
        if parameter == "precipitation":
            weather_result = f"NLDAS-3 precipitation for {location} ({date_range}): 45mm average from blob storage"
        elif parameter == "temperature":
            weather_result = f"NLDAS-3 temperature for {location} ({date_range}): 23°C average from blob storage"
        else:
            weather_result = f"NLDAS-3 {parameter} data for {location} ({date_range}): Retrieved from blob storage with AI search"
        
        response_message = {
            "Value": weather_result,
            "CorrelationId": messagepayload.get("CorrelationId", "")
        }
        logging.info(f'The function returns the following message through the output queue: {json.dumps(response_message)}')

        outputQueue.set(json.dumps(response_message))

    except Exception as e:
        logging.error(f"Error processing message: {e}")
        error_response = {
            "Value": f"Error processing NLDAS-3 data: {str(e)}",
            "CorrelationId": messagepayload.get("CorrelationId", "") if 'messagepayload' in locals() else ""
        }
        outputQueue.set(json.dumps(error_response))


# step2_with_your_credentials.py - Using your existing authentication method

import os
from azure.ai.projects import AIProjectClient
from azure.identity import ClientSecretCredential  # Use your existing method
from azure.ai.agents.models import AzureFunctionStorageQueue, AzureFunctionTool

# Use the same credentials you already have working
tenant_id = "4ba2629f-3085-4f9a-b2ec-3962de0e3490"
client_id = "768b7315-6661-498c-b826-c2689a5d790e"
client_secret = "l._8Q~bLceP-UjSOiTyil2~dAe92MPW6htpBFblU"

# Your storage info (you already have this working)
storage_account_name = "ainldas34950184597"
storage_service_endpoint = f"https://ainldas34754142228.vault.azure.net"

# Azure AI project endpoint (you'll need to get this from Azure AI Foundry)
project_endpoint = os.environ.get("PROJECT_ENDPOINT", "https://nldas-test-resource.services.ai.azure.com/api/projects/nldas-test/")
model_deployment_name = os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4")

# PART A: Define the NLDAS-3 Azure Function tool
nldas3_function_tool = AzureFunctionTool(
    name="nldas3_data_tool",
    description="Get NLDAS-3 meteorological forcing data including precipitation, temperature, wind, humidity, and radiation parameters. Data is retrieved from blob storage with AI search integration for hydrology and water resources applications.",
    parameters={
        "type": "object",
        "properties": {
            "parameter": {
                "type": "string", 
                "description": "The meteorological parameter to retrieve",
                "enum": ["precipitation", "temperature", "wind", "humidity", "radiation"]
            },
            "location": {
                "type": "string", 
                "description": "Geographic location or coordinates (e.g., 'Maryland', 'lat:39.0,lon:-76.8')"
            },
            "date_range": {
                "type": "string", 
                "description": "Date range in YYYY-MM format (e.g., '2024-01')"
            },
            "data_type": {
                "type": "string", 
                "description": "Data resolution type",
                "enum": ["monthly", "daily", "hourly"],
                "default": "monthly"
            },
            "outputqueueuri": {
                "type": "string", 
                "description": "The full output queue URI (automatically set by system)"
            }
        },
        "required": ["parameter", "location"]
    },
    input_queue=AzureFunctionStorageQueue(
        queue_name="azure-function-foo-input",
        storage_service_endpoint=storage_service_endpoint,
    ),
    output_queue=AzureFunctionStorageQueue(
        queue_name="azure-function-foo-output", 
        storage_service_endpoint=storage_service_endpoint,
    ),
)

print("NLDAS-3 Function Tool Configuration:")
print(f"Name: {nldas3_function_tool.name}")
print(f"Storage endpoint: {storage_service_endpoint}")

# PART B: Initialize AI client with YOUR existing credentials
try:
    # Use the same credential method that works for your blob storage
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    # Initialize the AIProjectClient with your credentials
    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=credential  # Use your working credentials instead of DefaultAzureCredential
    )
    
    # Create an agent with the NLDAS-3 Function tool
    agent = project_client.agents.create_agent(
        model=model_deployment_name,
        name="nldas3-copilot-agent",
        instructions=(
            "You are a helpful NLDAS-3 meteorological data assistant. Use the provided function to retrieve "
            "NLDAS-3 forcing data including precipitation, temperature, wind, humidity, and radiation data. "
            "The data is stored in blob storage and embedded using AI search for efficient retrieval. "
            "When you invoke the function, ALWAYS specify the output queue URI parameter as "
            f"'{storage_service_endpoint}/azure-function-foo-output'. "
            "Provide detailed explanations of the meteorological data and its applications in hydrology and water resources. "
            "Always respond with helpful context about the NLDAS-3 data you retrieve."
        ),
        tools=nldas3_function_tool.definitions,
    )
    print(f"✅ Created NLDAS-3 agent successfully!")
    print(f"Agent ID: {agent.id}")
    
except Exception as e:
    print(f"❌ Error creating AI agent: {e}")
    print("\n🔧 What you need:")
    print("1. PROJECT_ENDPOINT - from Azure AI Foundry")
    print("2. MODEL_DEPLOYMENT_NAME - deployed model name")
    print("3. Make sure your service principal has AI Foundry permissions")
    
    print(f"\n📋 Current settings:")
    print(f"Project endpoint: {project_endpoint}")
    print(f"Model deployment: {model_deployment_name}")
    print(f"Using tenant: {tenant_id}")
    print(f"Using client: {client_id}")