# agents/agent_chat.py - Fixed version with better timeout and error handling
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging
import time
from .dynamic_code_generator import execute_custom_code

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

def handle_chat_request(data):
    """
    Fixed version with better timeout handling and result return without agent loops
    """
    try:
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        logging.info(f"Processing chat request: {user_query}")

        # Create a thread for the conversation
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")
        
        # Enhanced query for better code generation
        # Update enhanced_query around line 65:

        # Update the enhanced_query around line 65:

        enhanced_query = f"""Use execute_custom_code to write Python code for: {user_query}

        Available functions and data:
        - load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day) - loads NLDAS-3 data
        - save_plot_to_blob_simple(figure, filename, account_key) - saves static plots and RETURNS the viewable URL
        - save_geojson_to_blob(data, filename, account_key) - saves interactive data as GeoJSON
        - create_azure_map_html(data_url, variable, center) - creates interactive Azure Maps
        - find_available_kerchunk_files(ACCOUNT_NAME, account_key) - lists available dates
        - NLDAS-3 variables: 'Tair' (temperature), 'Rainf' (precipitation), 'Qair' (humidity)
        - Available dates: January 1-31, 2023

        For static visualizations (matplotlib):
        - Create figures: fig, ax = plt.subplots(figsize=(12, 8))
        - Choose colormaps: 'RdYlBu_r' for temperature, 'Blues' for precipitation
        - Save: url = save_plot_to_blob_simple(fig, 'filename.png', account_key)
        - Set result = url

        For interactive visualizations (Azure Maps):
        - Convert data to GeoJSON: geojson_url = save_geojson_to_blob(data, 'filename.geojson', account_key)
        - Create interactive map: html_url = create_azure_map_html(geojson_url, 'temperature', [39.0, -76.5])
        - Set result = html_url (users get zoomable, interactive map)

        Choose interactive for: "interactive", "zoomable", "explore", "Azure Maps"
        Choose static for: "quick", "simple", "plot", "chart"

        For calculations: Set result = your_calculated_number
        Always set result = your_result_value at the end."""
        
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
        
        # Execution loop with better timeout handling
        max_iterations = 8  # Reduced from 10
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        final_response_content = None
        
        while run.status in ["queued", "in_progress", "requires_action"] and iteration < max_iterations:
            iteration += 1
            logging.info(f"Run status: {run.status} (iteration {iteration})")
            
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    logging.info(f"Function call requested: {func_name}")
                    
                    if func_name == "execute_custom_code":
                        if custom_code_executed:
                            # Skip duplicate calls
                            logging.info("Custom code already executed, skipping")
                            continue
                        
                        try:
                            function_args = json.loads(tool_call.function.arguments)
                            logging.info(f"Executing: {function_args.get('user_request', 'Unknown')}")
                            
                            # Execute the code
                            analysis_result = execute_custom_code(function_args)
                            analysis_data = analysis_result
                            custom_code_executed = True
                            
                            # Build response based on result
                            if analysis_result.get("status") == "success":
                                result_value = analysis_result.get("result", "No result")
                                user_request = function_args.get("user_request", "").lower()
                                
                                # Create user-friendly response content
                                if isinstance(result_value, (int, float)):
                                    if "temperature" in user_request:
                                        if result_value > 200:  # Likely Kelvin
                                            celsius = result_value - 273.15
                                            final_response_content = f"The temperature is {result_value:.2f} K ({celsius:.2f} °C)."
                                        else:
                                            final_response_content = f"The temperature is {result_value:.2f} °C."
                                    elif "precipitation" in user_request:
                                        final_response_content = f"The precipitation is {result_value:.6f} kg/m²/s."
                                    else:
                                        final_response_content = f"The calculated value is {result_value:.6f}."
                                else:
                                    final_response_content = f"Analysis completed. Result: {result_value}"
                                
                                # Create MINIMAL tool output to avoid timeout
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({
                                        "status": "success",
                                        "completed": True
                                    })
                                })
                                
                                # BREAK EARLY - Don't wait for agent to process further
                                logging.info("Code executed successfully, returning result immediately")
                                break
                                
                            else:
                                error_msg = analysis_result.get("error", "Unknown error")
                                final_response_content = f"I encountered an error: {error_msg}"
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({
                                        "status": "error",
                                        "error": error_msg[:100]  # Truncate
                                    })
                                })
                            
                        except Exception as e:
                            logging.error(f"Execution error: {e}")
                            final_response_content = f"Code execution failed: {str(e)}"
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": json.dumps({
                                    "status": "error",
                                    "error": str(e)[:100]
                                })
                            })
                    
                    else:
                        # Skip other functions to avoid complexity
                        logging.info(f"Skipping function: {func_name}")
                
                # Submit outputs with retry logic
                if tool_outputs:
                    max_retries = 2
                    for retry in range(max_retries):
                        try:
                            logging.info(f"Submitting tool outputs (attempt {retry + 1}/{max_retries})")
                            run = project_client.agents.runs.submit_tool_outputs(
                                thread_id=thread.id,
                                run_id=run.id,
                                tool_outputs=tool_outputs
                            )
                            logging.info(f"Successfully submitted {len(tool_outputs)} outputs")
                            break
                            
                        except Exception as e:
                            logging.error(f"Submit attempt {retry + 1} failed: {e}")
                            if retry == max_retries - 1:
                                # Final attempt failed, return result anyway
                                logging.warning("Tool output submission failed, but returning result")
                                if custom_code_executed and final_response_content:
                                    return {
                                        "status": "success",
                                        "content": final_response_content,
                                        "type": "direct_result_return", 
                                        "agent_id": text_agent_id,
                                        "thread_id": thread.id,
                                        "warning": "Tool output submission failed but code executed successfully",
                                        "analysis_data": analysis_data
                                    }
                                break
                            time.sleep(1)  # Wait before retry
                
                # If code executed successfully, return immediately
                if custom_code_executed and final_response_content:
                    logging.info("Returning result without waiting for agent completion")
                    return {
                        "status": "success",
                        "content": final_response_content,
                        "type": "early_return_success", 
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "debug": {
                            "iterations": iteration,
                            "custom_code_executed": True,
                            "early_return": True
                        },
                        "analysis_data": analysis_data
                    }
            
            # Shorter polling interval
            time.sleep(0.5)
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"Get run error: {e}")
                # If we have a result, return it
                if custom_code_executed and final_response_content:
                    return {
                        "status": "success",
                        "content": final_response_content,
                        "type": "error_recovery_return", 
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "analysis_data": analysis_data
                    }
                break
        
        # Handle completion or return result we have
        if custom_code_executed and final_response_content:
            return {
                "status": "success",
                "content": final_response_content,
                "type": "final_result_return", 
                "agent_id": text_agent_id,
                "thread_id": thread.id,
                "debug": {
                    "iterations": iteration,
                    "custom_code_executed": True,
                    "final_status": run.status
                },
                "analysis_data": analysis_data
            }
        
        # Fallback - try to get agent response
        try:
            if run.status == "completed":
                messages = project_client.agents.messages.list(thread_id=thread.id)
                assistant_messages = [msg for msg in messages if msg.role == "assistant"]
                
                if assistant_messages:
                    agent_response = assistant_messages[0].content[0].text.value
                    if agent_response and agent_response.strip():
                        return {
                            "status": "success",
                            "content": agent_response,
                            "type": "agent_completion_return",
                            "agent_id": text_agent_id,
                            "thread_id": thread.id,
                            "analysis_data": analysis_data
                        }
        except Exception as e:
            logging.error(f"Error getting agent response: {e}")
        
        # Final fallback
        return {
            "status": "partial_success",
            "content": final_response_content or "Request processed but no clear result",
            "type": "fallback_return",
            "agent_id": text_agent_id,
            "thread_id": thread.id,
            "debug": {
                "iterations": iteration,
                "final_status": run.status,
                "custom_code_executed": custom_code_executed
            },
            "analysis_data": analysis_data
        }
        
    except Exception as e:
        logging.error(f"Request error: {e}", exc_info=True)
        return {
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__
        }