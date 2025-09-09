# Fixed Agent_client.py - Using DefaultAzureCredential for AI Foundry + Key Vault for Storage

from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import AzureFunctionStorageQueue, AzureFunctionTool

# Key Vault credentials (for storage access)
tenant_id = "4ba2629f-3085-4f9a-b2ec-3962de0e3490"
client_id = "768b7315-6661-498c-b826-c2689a5d790e"
client_secret = "l._8Q~bLceP-UjSOiTyil2~dAe92MPW6htpBFblU"
vault_url = "https://ainldas34754142228.vault.azure.net/"

# Storage info
storage_account_name = "ainldas34950184597"
storage_service_endpoint = f"https://{storage_account_name}.queue.core.windows.net"

# AI project info
project_endpoint = "https://nldas-test-resource.services.ai.azure.com/api/projects/nldas-test/"
model_deployment_name = "gpt-4"

print("🔐 Testing with DefaultAzureCredential for AI Foundry + Key Vault for Storage")
print("=" * 70)

# Step 1: Get storage credentials from Key Vault (existing approach)
print("1. Connecting to Key Vault for storage credentials...")
try:
    # Use ClientSecretCredential for Key Vault access
    kv_credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    kv_client = SecretClient(vault_url=vault_url, credential=kv_credential)
    
    # Get storage key from Key Vault
    storage_secret_name = "blob-storage"
    account_key = kv_client.get_secret(storage_secret_name).value
    
    print("Key Vault connection successful!")
    print(f"   Vault URL: {vault_url}")
    print(f"   Retrieved secret: {storage_secret_name}")
    print(f"   Storage key length: {len(account_key)} characters")
    
except Exception as e:
    print(f"Key Vault connection failed: {e}")
    exit(1)

# Step 2: Create AI Project Client with DefaultAzureCredential
print("\n2. Creating AI Project Client with DefaultAzureCredential...")
try:
    # Use DefaultAzureCredential for AI Foundry (from your az login)
    ai_credential = DefaultAzureCredential()
    
    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=ai_credential  # Using DefaultAzureCredential here
    )
    
    print("AI Project Client created with DefaultAzureCredential!")
    print(f"   Endpoint: {project_endpoint}")
    print("   Using credentials from: az login")
    
except Exception as e:
    print(f"AI Project Client failed: {e}")
    print("   Make sure you ran 'az login' and have proper permissions")
    exit(1)

# Step 3: Configure NLDAS-3 Function Tool (using storage endpoint)
print("\n3. Configuring NLDAS-3 Function Tool...")
try:
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
    
    print("Function tool configured!")
    print(f"   Storage endpoint: {storage_service_endpoint}")
    print("   Tool created successfully")
    
except Exception as e:
    print(f"Tool configuration failed: {e}")
    exit(1)

# Step 4: Test listing agents (to verify AI Foundry permissions)
print("\n4. Testing AI Foundry permissions...")
try:
    agents = list(project_client.agents.list_agents())
    print(f"Successfully listed {len(agents)} existing agents")
    print("   AI Foundry permissions working correctly!")
    
except Exception as e:
    print(f"Failed to list agents: {e}")
    print("   This suggests permission issues with AI Foundry")
    exit(1)

# Step 5: Create Multi-Agent System
print("\n5. Creating Multi-Agent System...")

try:
    # Create GPT-4 Agent for generating answers
    gpt4_agent = project_client.agents.create_agent(
        model="gpt-4",  # GPT-4 for textual answers
        name="nldas3-gpt4-agent",
        instructions=(
            "You are a helpful assistant for answering meteorological and hydrological questions. "
            "Provide detailed and accurate textual answers based on the user's query."
        ),
        tools=[]  # No additional tools for GPT-4
    )
    print(f"GPT-4 Agent created successfully! Agent ID: {gpt4_agent.id}")

    # Store the Agent ID for later use
    gpt4_agent_id = gpt4_agent.id

    # Create GPT-Image-1 Agent for visualizing answers
    gpt_image_agent = project_client.agents.create_agent(
        model="gpt-image-1",  # GPT-Image-1 for visualizations
        name="nldas3-gpt-image-agent",
        instructions=(
            "You are a visualization assistant. Based on the input provided, generate visual representations "
            "such as charts, graphs, or images to help users better understand the data."
        ),
        tools=[]  # No additional tools for GPT-Image-1
    )
    print(f"GPT-Image-1 Agent created successfully! Agent ID: {gpt_image_agent.id}")

    # Store agent IDs for later use
    agents = {
        "gpt4_agent_id": gpt4_agent.id,
        "gpt_image_agent_id": gpt_image_agent.id
    }
    print("Multi-Agent System configured successfully!")

except Exception as e:
    print(f"Multi-Agent System creation failed: {e}")
    exit(1)

# Step 6: Create NLDAS-3 Agent
print("\n6. Creating NLDAS-3 Agent...")
try:
    agent = project_client.agents.create_agent(
        model=model_deployment_name,
        name="nldas3-copilot-agent-hybrid-auth",
        instructions=(
            "You are a helpful NLDAS-3 meteorological data assistant. Use the provided function to retrieve "
            "NLDAS-3 forcing data including precipitation, temperature, wind, humidity, and radiation data. "
            "The data is stored in blob storage and embedded using AI search for efficient retrieval. "
            f"When you invoke the function, ALWAYS specify the output queue URI parameter as "
            f"'{storage_service_endpoint}/azure-function-foo-output'. "
            "Provide detailed explanations of the meteorological data and its applications in hydrology and water resources."
        ),
        tools=nldas3_function_tool.definitions,
    )
    
    print("NLDAS-3 Agent created successfully!")
    print(f"   Agent ID: {agent.id}")
    print(f"   Model: {model_deployment_name}")
    print("   AI Foundry: DefaultAzureCredential (az login)")
    print("   Storage: Key Vault secrets")
    print("   Function tool attached")
    
    # Clean up test agent
    print("\n🧹 Cleaning up test agent...")
    project_client.agents.delete_agent(agent.id)
    print("Test agent deleted")
    
except Exception as e:
    print(f" Agent creation failed: {e}")
    print("   This might be because:")
    print("   - Missing Azure AI Foundry permissions")
    print("   - Model 'gpt-4' not deployed in your AI project")
    print("   - Agent with similar name already exists")

print("\n" + "=" * 70)
print("Hybrid Authentication Test Summary:")
print("Key Vault integration working (for storage)")
print("DefaultAzureCredential working (for AI Foundry)")
print("Function tool configuration working") 
print("Best of both worlds: secure + convenient")
print("\nNext: Test your Azure Function with 'func start'")