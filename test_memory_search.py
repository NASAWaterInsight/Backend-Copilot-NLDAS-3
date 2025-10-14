import os
import sys
import json

# Load environment variables from local.settings.json
def load_local_settings():
    """Load local.settings.json into environment variables"""
    try:
        with open('local.settings.json', 'r') as f:
            settings = json.load(f)
        for key, value in settings.get('Values', {}).items():
            os.environ[key] = value
        print(f"✅ Loaded {len(settings.get('Values', {}))} settings")
        return True
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        return False

# Load settings first
print("🔧 Loading configuration...")
load_local_settings()

# Test Mem0 configuration
print("\n🧪 Testing Mem0 Configuration...")
print(f"Search Service: {os.getenv('MEM0_SERVICE_NAME')}")
print(f"Search Key: {'SET' if os.getenv('MEM0_API_KEY') else 'NOT SET'}")
print(f"OpenAI Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
print(f"OpenAI Key: {'SET' if os.getenv('AZURE_OPENAI_API_KEY') else 'NOT SET'}")
print(f"Embed Model: {os.getenv('MEM0_EMBED_MODEL', 'text-embedding-ada-002')}")
print(f"Chat Model: {os.getenv('MEM0_CHAT_MODEL', 'gpt-4o')}")

# Test direct Azure AI Search connection
print("\n🔍 Testing Azure AI Search Connection...")
try:
    from azure.search.documents import SearchClient
    from azure.core.credentials import AzureKeyCredential
    
    search_client = SearchClient(
        endpoint=f"https://{os.getenv('MEM0_SERVICE_NAME')}.search.windows.net",
        index_name=os.getenv('MEM0_COLLECTION_NAME', 'nldas_memories'),
        credential=AzureKeyCredential(os.getenv('MEM0_API_KEY'))
    )
    
    # Test connection
    search_results = search_client.search("*", top=1)
    doc_count = sum(1 for _ in search_results)
    print(f"✅ Azure AI Search connection successful")
    print(f"   Service: {os.getenv('MEM0_SERVICE_NAME')}")
    print(f"   Index: {os.getenv('MEM0_COLLECTION_NAME', 'nldas_memories')}")
    
except Exception as search_error:
    print(f"❌ Azure AI Search connection failed: {search_error}")

# Test OpenAI embeddings connection
print("\n🤖 Testing Azure OpenAI Embeddings...")
try:
    from openai import AzureOpenAI
    
    client = AzureOpenAI(
        api_key=os.getenv('AZURE_OPENAI_API_KEY'),
        api_version="2024-12-01-preview",
        azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT')
    )
    
    # Test embedding
    response = client.embeddings.create(
        input="test weather query",
        model=os.getenv('MEM0_EMBED_MODEL', 'text-embedding-ada-002')
    )
    
    embedding_dims = len(response.data[0].embedding)
    print(f"✅ Azure OpenAI Embeddings working")
    print(f"   Model: {os.getenv('MEM0_EMBED_MODEL', 'text-embedding-ada-002')}")
    print(f"   Dimensions: {embedding_dims}")
    
except Exception as openai_error:
    print(f"❌ Azure OpenAI Embeddings failed: {openai_error}")

# Test Mem0 initialization and search
print("\n🧠 Testing Mem0 Memory Manager...")
try:
    from agents.memory_manager import memory_manager
    
    if memory_manager.enabled:
        print("✅ Memory Manager: Enabled")
        
        # Test adding a memory
        test_user = "test-search-user"
        test_memory = "User requested temperature analysis for Michigan in June 2023"
        
        print(f"📝 Adding test memory: {test_memory}")
        memory_id = memory_manager.add(test_memory, user_id=test_user, meta={"type": "test"})
        
        if memory_id:
            print(f"✅ Memory added with ID: {memory_id}")
            
            # Test searching for the memory
            import time
            print("⏱️ Waiting 2 seconds for indexing...")
            time.sleep(2)
            
            print("🔍 Testing semantic search...")
            search_queries = [
                "temperature Michigan",
                "weather analysis Michigan June",
                "Michigan temperature June 2023",
                "show me temperature data"
            ]
            
            for query in search_queries:
                print(f"\n   Query: '{query}'")
                results = memory_manager.search(query, user_id=test_user, limit=3)
                
                if results:
                    print(f"   ✅ Found {len(results)} results")
                    for i, result in enumerate(results):
                        if isinstance(result, dict):
                            memory_text = result.get('memory', result.get('text', ''))
                            score = result.get('score', 0.0)
                            print(f"      [{i+1}] Score: {score:.3f} - {memory_text[:50]}...")
                        else:
                            print(f"      [{i+1}] {result}")
                else:
                    print(f"   ❌ No results found")
            
            # Clean up test memory
            try:
                memory_manager.delete_all_user_memories(test_user)
                print(f"🗑️ Cleaned up test memories for {test_user}")
            except:
                pass
                
        else:
            print("❌ Failed to add test memory")
    else:
        print("❌ Memory Manager: Disabled")
        
except Exception as mem_error:
    print(f"❌ Memory Manager Error: {mem_error}")
    import traceback
    print(f"   Traceback: {traceback.format_exc()}")

print("\n📋 Test Summary:")
print("This test verifies that:")
print("1. Azure AI Search can connect and store documents")
print("2. Azure OpenAI can generate embeddings for semantic search")  
print("3. Mem0 can combine both for intelligent memory retrieval")
print("4. The memory system can find relevant context for weather queries")
