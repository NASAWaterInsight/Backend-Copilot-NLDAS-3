# test_memory_setup.py
import os
import sys
import json
sys.path.append('.')

# CRITICAL: Load local.settings.json into environment variables
def load_local_settings():
    """Load local.settings.json into environment variables for testing"""
    try:
        with open('local.settings.json', 'r') as f:
            settings = json.load(f)
            
        # Load all Values into os.environ
        for key, value in settings.get('Values', {}).items():
            os.environ[key] = value
            
        print(f"✅ Loaded {len(settings.get('Values', {}))} settings from local.settings.json")
        return True
        
    except FileNotFoundError:
        print("❌ local.settings.json not found")
        return False
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        return False

# Load settings first
print("🔧 Loading local.settings.json...")
if not load_local_settings():
    print("⚠️ Continuing with system environment variables only...")

# Test environment variables - FIXED to match your local.settings.json
print("\n🧪 Testing Memory Configuration...")
print(f"✅ Search Service: {os.getenv('MEM0_SERVICE_NAME', 'NOT SET')}")
print(f"✅ Search Key: {'SET' if os.getenv('MEM0_API_KEY') else 'NOT SET'}")
print(f"✅ Collection Name: {os.getenv('MEM0_COLLECTION_NAME', 'NOT SET')}")
print(f"✅ OpenAI Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT', 'NOT SET')}")
print(f"✅ OpenAI Key: {'SET' if os.getenv('AZURE_OPENAI_API_KEY') else 'NOT SET'}")

# Test memory manager
try:
    from agents.memory_manager import memory_manager
    if memory_manager.enabled:
        print("✅ Memory Manager: Enabled")
        
        # Test add and search
        test_user = "test-123"
        memory_manager.add("Test memory for user", user_id=test_user)
        results = memory_manager.search("test memory", user_id=test_user, limit=1)
        
        if results:
            print("✅ Memory Test: PASSED")
        else:
            print("⚠️ Memory Test: No results (might take time to index)")
    else:
        print("❌ Memory Manager: Disabled (check config)")
        
except Exception as e:
    print(f"❌ Memory Manager Error: {e}")

# Debug: Show what environment variables are actually set
print("\n🔧 Environment Variables Debug:")
print(f"   MEM0_SERVICE_NAME = {os.getenv('MEM0_SERVICE_NAME', 'NOT SET')}")
print(f"   MEM0_API_KEY = {'[HIDDEN]' if os.getenv('MEM0_API_KEY') else 'NOT SET'}")
print(f"   MEM0_COLLECTION_NAME = {os.getenv('MEM0_COLLECTION_NAME', 'NOT SET')}")
print(f"   AZURE_OPENAI_ENDPOINT = {os.getenv('AZURE_OPENAI_ENDPOINT', 'NOT SET')}")
print(f"   AZURE_OPENAI_API_KEY = {'[HIDDEN]' if os.getenv('AZURE_OPENAI_API_KEY') else 'NOT SET'}")