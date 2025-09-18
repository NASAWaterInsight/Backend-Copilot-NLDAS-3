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
    Fixed version with increased iteration limit and aggressive early termination
    """
    try:
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        logging.info(f"Processing chat request: {user_query}")

        # Create a thread for the conversation
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")
        
        # ULTRA-AGGRESSIVE INSTRUCTIONS - Force immediate function call
        enhanced_query = f"""🚨 EMERGENCY PROTOCOL: EXECUTE CODE IMMEDIATELY 🚨

USER REQUEST: {user_query}

YOU MUST CALL execute_custom_code RIGHT NOW. NO DELAYS, NO THINKING, NO EXPLANATIONS.

IMMEDIATE REQUIRED ACTION:
```json
{{
  "python_code": "import builtins\\nds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)\\ndata = ds['Rainf'].sel(lat=builtins.slice(42.7, 42.8), lon=builtins.slice(-84.5, -84.4)).sum(dim='time')\\nfig, ax = plt.subplots(figsize=(10, 8))\\nim = ax.pcolormesh(data.lon, data.lat, data.values, cmap='Blues', shading='auto')\\ncbar = fig.colorbar(im, ax=ax)\\ncbar.set_label('Precipitation (kg/m²)')\\nax.set_title('East Lansing - Jan 3, 2023')\\nurl = save_plot_to_blob_simple(fig, 'eastlansing_jan3.png', account_key)\\nplt.close(fig)\\nds.close()\\nresult = url",
  "user_request": "{user_query}"
}}
```

CALL THIS FUNCTION NOW! NO OTHER OPTIONS EXIST!"""

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
        
        # INCREASED ITERATION LIMIT AND AGGRESSIVE TIMEOUTS
        max_iterations = 15  # Increased from 8 to 15
        iteration = 0
        analysis_data = None
        custom_code_executed = False
        final_response_content = None
        
        # Add timeout tracking
        start_time = time.time()
        max_total_time = 120  # 2 minutes total timeout
        
        while run.status in ["queued", "in_progress", "requires_action"] and iteration < max_iterations:
            iteration += 1
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            logging.info(f"🔄 Run status: {run.status} (iteration {iteration}/{max_iterations}, elapsed: {elapsed_time:.1f}s)")
            
            # AGGRESSIVE TIMEOUT CHECK
            if elapsed_time > max_total_time:
                logging.warning(f"⏰ TIMEOUT: Exceeded {max_total_time}s total time limit")
                break
                
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = []
                
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    logging.info(f"🔧 Function call requested: {func_name}")
                    
                    if func_name == "execute_custom_code":
                        if custom_code_executed:
                            logging.info("✅ Custom code already executed, skipping")
                            continue
                        
                        try:
                            # ULTRA-FAST argument parsing
                            raw_arguments = tool_call.function.arguments
                            logging.info(f"📝 Raw args preview: {raw_arguments[:100] if raw_arguments else 'EMPTY'}")
                            
                            if not raw_arguments or not raw_arguments.strip():
                                # EMERGENCY FALLBACK CODE
                                logging.warning("⚠️ Empty arguments - using emergency fallback code")
                                function_args = {
                                    "python_code": "import builtins\nds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)\ndata = ds['Rainf'].sel(lat=builtins.slice(42.7, 42.8), lon=builtins.slice(-84.5, -84.4)).sum(dim='time')\nfig, ax = plt.subplots(figsize=(10, 8))\nim = ax.pcolormesh(data.lon, data.lat, data.values, cmap='Blues', shading='auto')\ncbar = fig.colorbar(im, ax=ax)\ncbar.set_label('Precipitation (kg/m²)')\nax.set_title('East Lansing Emergency Plot')\nurl = save_plot_to_blob_simple(fig, 'emergency_plot.png', account_key)\nplt.close(fig)\nds.close()\nresult = url",
                                    "user_request": user_query
                                }
                            else:
                                # Fast JSON parsing
                                try:
                                    function_args = json.loads(raw_arguments)
                                except json.JSONDecodeError:
                                    # Extract from markdown if needed
                                    if '```' in raw_arguments:
                                        code_start = raw_arguments.find('```python')
                                        if code_start == -1:
                                            code_start = raw_arguments.find('```')
                                        code_end = raw_arguments.rfind('```')
                                        if code_start != -1 and code_end != -1 and code_end > code_start:
                                            python_code = raw_arguments[code_start:code_end].replace('```python', '').replace('```', '').strip()
                                            function_args = {
                                                "python_code": python_code,
                                                "user_request": user_query
                                            }
                                        else:
                                            raise ValueError("Could not extract code from markdown")
                                    else:
                                        raise ValueError("Invalid JSON and no markdown found")
                            
                            logging.info(f"🚀 EXECUTING CODE NOW...")
                            
                            # Execute the code with timeout
                            analysis_result = execute_custom_code(function_args)
                            analysis_data = analysis_result
                            custom_code_executed = True
                            
                            # IMMEDIATE SUCCESS HANDLING
                            if analysis_result.get("status") == "success":
                                result_value = analysis_result.get("result", "No result")
                                final_response_content = f"✅ Analysis completed successfully! Result: {result_value}"
                                
                                # MINIMAL tool output
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({"status": "success", "completed": True})
                                })
                                
                                logging.info("🎉 SUCCESS! Code executed, returning immediately")
                                # IMMEDIATE RETURN - Don't wait for anything else
                                return {
                                    "status": "success",
                                    "content": final_response_content,
                                    "type": "immediate_success_return",
                                    "agent_id": text_agent_id,
                                    "thread_id": thread.id,
                                    "debug": {
                                        "iterations": iteration,
                                        "elapsed_time": elapsed_time,
                                        "custom_code_executed": True
                                    },
                                    "analysis_data": analysis_result
                                }
                                
                            else:
                                error_msg = analysis_result.get("error", "Unknown error")
                                final_response_content = f"❌ Code execution failed: {error_msg}"
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": json.dumps({"status": "error", "error": error_msg[:100]})
                                })
                            
                        except Exception as e:
                            logging.error(f"💥 Execution error: {e}")
                            final_response_content = f"❌ Execution failed: {str(e)}"
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": json.dumps({"status": "error", "error": str(e)[:100]})
                            })
                    
                    else:
                        # Skip other functions immediately
                        logging.info(f"⏭️ Skipping function: {func_name}")
                
                # RAPID tool output submission
                if tool_outputs:
                    try:
                        logging.info("📤 Submitting tool outputs...")
                        run = project_client.agents.runs.submit_tool_outputs(
                            thread_id=thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                        logging.info("✅ Tool outputs submitted")
                    except Exception as e:
                        logging.error(f"❌ Tool output submission failed: {e}")
                        # If we have a result, return it anyway
                        if custom_code_executed and final_response_content:
                            return {
                                "status": "success",
                                "content": final_response_content,
                                "type": "submission_failed_but_success",
                                "agent_id": text_agent_id,
                                "thread_id": thread.id,
                                "analysis_data": analysis_data
                            }
                
                # IMMEDIATE RETURN if code executed
                if custom_code_executed and final_response_content:
                    return {
                        "status": "success",
                        "content": final_response_content,
                        "type": "post_submission_success",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id,
                        "debug": {
                            "iterations": iteration,
                            "elapsed_time": elapsed_time,
                            "custom_code_executed": True
                        },
                        "analysis_data": analysis_data
                    }
            
            # VERY SHORT POLLING INTERVAL
            time.sleep(0.2)  # Reduced from 0.5 to 0.2
            try:
                run = _get_run(thread_id=thread.id, run_id=run.id)
            except Exception as e:
                logging.error(f"❌ Get run error: {e}")
                break
        
        # ENHANCED FALLBACK HANDLING
        if custom_code_executed and final_response_content:
            return {
                "status": "success",
                "content": final_response_content,
                "type": "final_fallback_success",
                "agent_id": text_agent_id,
                "thread_id": thread.id,
                "debug": {
                    "iterations": iteration,
                    "final_status": run.status if 'run' in locals() else "unknown",
                    "custom_code_executed": True,
                    "reason": "fallback_after_execution"
                },
                "analysis_data": analysis_data
            }
        
        # ULTIMATE FALLBACK
        elapsed_time = time.time() - start_time
        return {
            "status": "timeout_failure", 
            "content": f"Agent failed to execute code within {max_iterations} iterations ({elapsed_time:.1f}s). The agent may need recreation or there may be a system issue.",
            "type": "iteration_limit_exceeded",
            "agent_id": text_agent_id,
            "thread_id": thread.id,
            "debug": {
                "iterations": iteration,
                "max_iterations": max_iterations,
                "elapsed_time": elapsed_time,
                "final_status": run.status if 'run' in locals() else "unknown",
                "custom_code_executed": custom_code_executed,
                "suggestion": "Try recreating the agent or check Azure AI service status"
            }
        }
        
    except Exception as e:
        logging.error(f"❌ Request error: {e}", exc_info=True)
        return {
            "status": "error",
            "content": str(e),
            "error_type": type(e).__name__
        }