from agents.memory_manager import memory_manager

print('Testing memory...')

# Test basic functionality
user_id = "test_user_123"

# Add a memory
memory_id = memory_manager.add(
    "Show me temperature map for Florida on March 15, 2023", 
    user_id, 
    {"type": "query", "variable": "temperature", "region": "Florida"}
)

print(f'Memory stored: {memory_id}')

# Search memories
results = memory_manager.search("temperature Florida", user_id)
print(f'Found memories: {len(results)}')

# Get recent context
context = memory_manager.recent_context(user_id)
print(f'Recent context: {context}')

# Test flash drought memory
flash_memory_id = memory_manager.add_flash_drought_analysis(
    user_id=user_id,
    region="Great Plains",
    start_period="Jun 2012",
    end_period="Aug 2012", 
    result_url="https://example.com/map.png",
    percentage_affected=25.3
)
print(f'Flash drought memory stored: {flash_memory_id}')

# Search for flash drought
flash_results = memory_manager.search("flash drought Great Plains", user_id)
print(f'Found flash drought memories: {len(flash_results)}')

print('Memory test completed!')
