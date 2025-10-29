import os
import json
import logging

# Load environment variables
with open('local.settings.json', 'r') as f:
    settings = json.load(f)
    for key, value in settings['Values'].items():
        if key.startswith(('MEM0_', 'AZURE_OPENAI_')):
            os.environ[key] = value

# Test basic connectivity
print("🔧 Testing Azure AI Search connectivity...")

try:
    from azure.search.documents import SearchClient
    from azure.core.credentials import AzureKeyCredential
    
    search_client = SearchClient(
        endpoint=f"https://{os.getenv('MEM0_SERVICE_NAME')}.search.windows.net",
        index_name=os.getenv('MEM0_COLLECTION_NAME', 'nldas_memories'),
        credential=AzureKeyCredential(os.getenv('MEM0_API_KEY'))
    )
    
    # Try to search (this will create index if it doesn't exist)
    results = list(search_client.search("*", top=1))
    print(f"✅ Azure AI Search connected - found {len(results)} documents")
    
except Exception as search_error:
    print(f"❌ Azure AI Search error: {search_error}")

print("\n🔧 Testing Azure OpenAI connectivity...")

try:
    from openai import AzureOpenAI
    
    client = AzureOpenAI(
        api_key=os.getenv('AZURE_OPENAI_API_KEY'),
        api_version=os.getenv('AZURE_OPENAI_API_VERSION'),
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT')
    )
    
    # Test embedding
    response = client.embeddings.create(
        model=os.getenv('MEM0_EMBED_MODEL'),
        input="test embedding"
    )
    
    print(f"✅ Azure OpenAI connected - embedding dimension: {len(response.data[0].embedding)}")
    
except Exception as openai_error:
    print(f"❌ Azure OpenAI error: {openai_error}")

print("\n🔧 Testing Mem0 with embeddings only...")

try:
    from mem0 import Memory
    
    # FIXED: Configuration with ONLY embeddings and vector store (no LLM)
    config = {
        "vector_store": {
            "provider": "azure_ai_search",
            "config": {
                "service_name": os.getenv("MEM0_SERVICE_NAME"),
                "api_key": os.getenv("MEM0_API_KEY"),
                "collection_name": "test_memories",
                "embedding_model_dims": 1536,
            },
        },
        "embedder": {
            "provider": "azure_openai",
            "config": {
                "model": "text-embedding-ada-002",
                "embedding_dims": 1536,
                "azure_kwargs": {
                    "api_version": "2024-10-21",
                    "azure_deployment": "text-embedding-ada-002",
                    "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                    "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                },
            },
        },
        # REMOVED: LLM configuration to avoid OpenAI API key issues
    }
    
    memory = Memory.from_config(config)
    
    # Test simple add with basic text
    result = memory.add("Test memory for debugging weather analysis", user_id="debug_user")
    print(f"✅ Mem0 add result: {result}")
    
    # Test search
    search_results = memory.search("test weather", user_id="debug_user")
    print(f"✅ Mem0 search results: {len(search_results.get('results', []))} memories found")
    
    # Test get_all
    all_memories = memory.get_all(user_id="debug_user")
    print(f"✅ Mem0 get_all: {len(all_memories.get('results', []))} total memories")
    
except Exception as mem0_error:
    print(f"❌ Mem0 error: {mem0_error}")
    import traceback
    traceback.print_exc()

print("\n🔧 Testing Mem0 with minimal config...")

try:
    from mem0 import Memory
    
    # Try the absolute minimal configuration
    config = {
        "vector_store": {
            "provider": "azure_ai_search",
            "config": {
                "service_name": os.getenv("MEM0_SERVICE_NAME"),
                "api_key": os.getenv("MEM0_API_KEY"),
                "collection_name": "test_memories_minimal",
                "embedding_model_dims": 1536,
            },
        },
    }
    
    # Try to create without embedder first
    print("Attempting minimal config (vector store only)...")
    memory = Memory.from_config(config)
    
    # Test simple operations
    result = memory.add("Simple test", user_id="test_user")
    print(f"✅ Minimal Mem0 working: {result}")
    
except Exception as minimal_error:
    print(f"❌ Minimal config failed: {minimal_error}")
    
    # Try with environment variable workaround
    try:
        print("Trying with OPENAI_API_KEY environment variable workaround...")
        
        # Set a dummy OpenAI API key to satisfy the check
        os.environ["OPENAI_API_KEY"] = "dummy-key-for-mem0"
        
        config_with_llm = {
            "vector_store": {
                "provider": "azure_ai_search",
                "config": {
                    "service_name": os.getenv("MEM0_SERVICE_NAME"),
                    "api_key": os.getenv("MEM0_API_KEY"),
                    "collection_name": "test_memories_workaround",
                    "embedding_model_dims": 1536,
                },
            },
            "embedder": {
                "provider": "azure_openai",
                "config": {
                    "model": "text-embedding-ada-002",
                    "embedding_dims": 1536,
                    "azure_kwargs": {
                        "api_version": "2024-10-21",
                        "azure_deployment": "text-embedding-ada-002",
                        "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                        "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                    },
                },
            },
            # Don't specify LLM at all - let it use the dummy key
        }
        
        memory = Memory.from_config(config_with_llm)
        result = memory.add("Test with workaround", user_id="test_user")
        print(f"✅ Workaround successful: {result}")
        
    except Exception as workaround_error:
        print(f"❌ Workaround also failed: {workaround_error}")

print("\n🔧 Testing full memory manager...")

try:
    from agents.memory_manager import memory_manager
    
    # Test the actual memory manager
    if memory_manager.enabled:
        print("✅ Memory manager is enabled")
        
        # Test add
        memory_id = memory_manager.add("Test query for weather analysis", "test_user", {"type": "query"})
        print(f"✅ Memory manager add: {memory_id}")
        
        # Test search
        results = memory_manager.search("weather analysis", "test_user")
        print(f"✅ Memory manager search: {len(results)} results")
        
        # Test recent context
        context = memory_manager.recent_context("test_user")
        print(f"✅ Memory manager context: {len(context)} items")
        
    else:
        print("❌ Memory manager is not enabled")
        
except Exception as manager_error:
    print(f"❌ Memory manager error: {manager_error}")
    import traceback
    traceback.print_exc()
