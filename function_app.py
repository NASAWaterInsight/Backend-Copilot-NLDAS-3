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
def queue_trigger(inputQueue: func.QueueMessage, outputQueue: func.Out[str]):
    try:
        messagepayload = json.loads(inputQueue.get_body().decode("utf-8"))
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


