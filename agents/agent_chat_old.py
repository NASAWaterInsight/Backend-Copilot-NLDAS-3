# agents/agent_chat.py
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os
import json
import logging

# Load agent info
agent_info_path = os.path.join(os.path.dirname(__file__), "../agent_info.json")
try:
    with open(agent_info_path, "r") as f:
        agent_info = json.load(f)
    
    # Extract text agent ID from the correct nested structure
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

def handle_chat_request(data):
    """
    Handles chat requests by sending the input to the GPT-4o text agent with Azure AI Search capabilities.

    Args:
        data (dict): The input data containing the query for NLDAS-3 data.

    Returns:
        dict: Response containing the agent's answer or error message.
    """
    try:
        # Extract user query from data
        user_query = data.get("input", data.get("query", "Tell me about NLDAS-3 data"))
        
        logging.info(f"Processing chat request: {user_query}")
        
        # Create a thread for the conversation
        thread = project_client.agents.threads.create()
        logging.info(f"Created thread: {thread.id}")
        
        # Add user message to the thread
        message = project_client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_query
        )
        logging.info(f"Created message: {message.id}")
        
        # Run the text agent (with Azure AI Search capabilities)
        run = project_client.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=text_agent_id
        )
        logging.info(f"Agent run completed with status: {run.status}")
        
        # Get the response
        if run.status == "completed":
            # Retrieve messages from the thread
            messages = project_client.agents.messages.list(thread_id=thread.id)
            
            # Get the assistant's latest response
            for msg in messages:
                if msg.role == "assistant":
                    response_content = msg.content[0].text.value if msg.content else "No response generated"
                    
                    return {
                        "status": "success",
                        "content": response_content,
                        "type": "text_response",
                        "agent_id": text_agent_id,
                        "thread_id": thread.id
                    }
        
        # Handle failed runs
        error_message = f"Agent run failed with status: {run.status}"
        if hasattr(run, 'last_error') and run.last_error:
            error_message += f" - {run.last_error}"
            
        return {
            "status": "error",
            "content": error_message,
            "agent_id": text_agent_id
        }
        
    except Exception as e:
        error_msg = f"Error processing chat request: {str(e)}"
        logging.error(error_msg)
        return {
            "status": "error",
            "content": error_msg
        }