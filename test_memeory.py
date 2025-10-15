import os
import json
from agents.memory_manager import memory_manager

def main():
    print("🧠 Memory Smoke Test")
    print("=" * 50)
    
    # Check environment status
    diag = memory_manager.validate_env()
    print(f"Memory Enabled: {diag['enabled']}")
    print(f"Missing vars: {diag['missing']}")
    print(f"Error count: {diag['errors']}")
    
    if not diag["enabled"]:
        print("\n❌ Memory not enabled. Set these environment variables:")
        for var in diag["missing"]:
            print(f"   export {var}=<your-value>")
        print("\nThen restart and run this test again.")
        return
    
    print("\n📝 Testing memory operations...")
    
    # Test user
    user_id = "smoke-test-user"
    
    # Add a structured memory
    print("Adding structured memory...")
    memory_manager.add_structured(
        user_id=user_id,
        variable="Tair",
        region="florida",
        date_str="2023-05",
        bounds={"north": 31.0, "south": 24.5, "east": -80.0, "west": -87.6},
        color_range={"min": 15.2, "max": 28.9}
    )
    
    # Add a summary memory
    print("Adding summary memory...")
    memory_manager.add(
        "[MAP_SUMMARY] Florida temperature map May 2023 showing warm coastal areas",
        user_id=user_id,
        meta={"type": "map_summary"}
    )
    
    # Search for memories
    print("Searching memories...")
    results = memory_manager.search("florida temperature", user_id=user_id, limit=3)
    
    print(f"\nFound {len(results)} memories:")
    for i, result in enumerate(results):
        print(f"  {i+1}. {result.get('memory', 'N/A')}")
    
    # Test recent context
    print("\nTesting recent context...")
    recent = memory_manager.recent_context(user_id, limit=2)
    print(f"Recent context entries: {len(recent)}")
    
    print("\n✅ Memory smoke test completed successfully!")
    print("Now you can test map queries with memory persistence.")

if __name__ == "__main__":
    main()