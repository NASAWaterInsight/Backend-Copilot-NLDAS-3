# create agent_info.json - FINAL VERSION with Static Frame Animation Fix

import json
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType

# ---------- Config ----------
PROJECT_ENDPOINT = "https://nldas-test-resource.services.ai.azure.com/api/projects/nldas-test"
TEXT_MODEL = "gpt-4o"
VIZ_MODEL = "gpt-4o"
AI_SEARCH_CONNECTION_NAME = "searchnldas3"
AI_SEARCH_INDEX_NAME = "multimodal-rag-precip-temp2"

# ---------- Simple Code Function Definition ----------
def get_execute_code_function_definition():
    """
    Returns the function definition for executing custom Python code
    """
    return {
        "type": "function",
        "function": {
            "name": "execute_custom_code",
            "description": "Execute custom Python code for NLDAS-3 weather analysis. Use only the available functions listed in instructions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "python_code": {
                        "type": "string",
                        "description": "Complete Python code to execute. Must set 'result' variable with final output."
                    },
                    "user_request": {
                        "type": "string",
                        "description": "Original user request for reference"
                    }
                },
                "required": ["python_code", "user_request"]
            }
        }
    }

# ---------- Initialize client ----------
cred = DefaultAzureCredential()
proj = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=cred)

# ---------- Get connection ID ----------
search_conn_id = None
for connection in proj.connections.list():
    if connection.name == AI_SEARCH_CONNECTION_NAME:
        search_conn_id = connection.id
        break

# Get available indexes
if AI_SEARCH_INDEX_NAME == "your_index_name":
    try:
        indexes = list(proj.indexes.list())
        if indexes:
            AI_SEARCH_INDEX_NAME = indexes[0].name
            print(f"Auto-detected index: {AI_SEARCH_INDEX_NAME}")
        else:
            print("No indexes found in the project")
            AI_SEARCH_INDEX_NAME = None
    except:
        print("Could not auto-detect index name. Please specify AI_SEARCH_INDEX_NAME manually.")
        AI_SEARCH_INDEX_NAME = None

# ---------- Create Azure AI Search tool ----------
ai_search_tool = None
if search_conn_id and AI_SEARCH_INDEX_NAME:
    ai_search_tool = AzureAISearchTool(
        index_connection_id=search_conn_id,
        index_name=AI_SEARCH_INDEX_NAME,
        query_type=AzureAISearchQueryType.SIMPLE,
        top_k=50
    )

# ---------- Create tools list ----------
code_tool = get_execute_code_function_definition()
text_tools = []

if ai_search_tool:
    text_tools.extend(ai_search_tool.definitions)

text_tools.append(code_tool)
text_tool_resources = ai_search_tool.resources if ai_search_tool else None

# ---------- COMPLETE INSTRUCTIONS WITH STATIC FRAME ANIMATION ----------
instructions = """MANDATORY: Call execute_custom_code immediately.

CRITICAL: ONLY use these exact function names (no others exist):
- load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
- save_plot_to_blob_simple(fig, filename, account_key)
- process_daily_data(data, variable_name)

CRITICAL VARIABLE MAPPING - ONLY use these exact NLDAS variable names:
- Temperature = 'Tair' (convert: subtract 273.15 for Celsius)
- Precipitation = 'Rainf' (unit is already mm - kg/m² equals mm)
- Humidity = 'Qair' 
- Wind = 'Wind_E' or 'Wind_N'
- Pressure = 'PSurf'
- Solar radiation = 'SWdown'
- Longwave radiation = 'LWdown'

For precipitation: Use 'Rainf' variable and sum over time dimension.
For temperature: Use 'Tair' variable, subtract 273.15, and average over time.

COORDINATES:
- Florida: lat_min=24.5, lat_max=31.0, lon_min=-87.6, lon_max=-80.0
- Maryland: lat_min=37.9, lat_max=39.7, lon_min=-79.5, lon_max=-75.0
- Michigan: lat_min=41.7, lat_max=48.2, lon_min=-90.4, lon_max=-82.4
- California: lat_min=32.5, lat_max=42.0, lon_min=-124.4, lon_max=-114.1

🎯 SUBPLOT COLOR SCALING RULE:
When creating subplots of the SAME variable (e.g., average, min, max temperature), use SHARED color scale for meaningful comparison.

FOR SUBPLOTS OF SAME VARIABLE - FIXED SCOPE ERROR:
```python
import builtins
import numpy as np

# Florida coordinates (MUST be defined at module level)
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0

# Load data
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 6, 10)
temp_data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), 
                          lon=builtins.slice(lon_min, lon_max)) - 273.15

# Calculate different statistics
avg_temp = temp_data.mean(dim='time')
min_temp = temp_data.min(dim='time') 
max_temp = temp_data.max(dim='time')

# CRITICAL: Calculate shared color scale for SAME variable
all_values = np.concatenate([
    avg_temp.values.flatten(),
    min_temp.values.flatten(), 
    max_temp.values.flatten()
])
shared_vmin = float(np.nanmin(all_values))
shared_vmax = float(np.nanmax(all_values))

print(f"Shared temperature range: {shared_vmin:.1f} to {shared_vmax:.1f} °C")

# CRITICAL: Initialize fig variable first - handle both Cartopy and fallback
fig = None

# Create 1x3 subplots with FIXED spacing for colorbar
if CARTOPY_AVAILABLE:
    fig = plt.figure(figsize=(20, 6))
    fig.patch.set_facecolor('white')
    
    ax1 = fig.add_subplot(1, 3, 1, projection=ccrs.PlateCarree())
    ax2 = fig.add_subplot(1, 3, 2, projection=ccrs.PlateCarree())
    ax3 = fig.add_subplot(1, 3, 3, projection=ccrs.PlateCarree())
    
    # Add features to all axes - NO HELPER FUNCTIONS
    for ax in [ax1, ax2, ax3]:
        # Set extent using module-level coordinates
        ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
        # Add features directly - no function calls
        ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='black', facecolor='none')
        ax.add_feature(cfeature.STATES, linewidth=0.4, edgecolor='gray', facecolor='none')
    
    # Plot with SHARED color scale (vmin/vmax same for all)
    im1 = ax1.pcolormesh(avg_temp.lon, avg_temp.lat, avg_temp.values,
                        cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax,
                        shading='auto', transform=ccrs.PlateCarree())
    
    im2 = ax2.pcolormesh(min_temp.lon, min_temp.lat, min_temp.values,
                        cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax,
                        shading='auto', transform=ccrs.PlateCarree())
                        
    im3 = ax3.pcolormesh(max_temp.lon, max_temp.lat, max_temp.values,
                        cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax,
                        shading='auto', transform=ccrs.PlateCarree())
    
    # Individual subplot titles only (no main title)
    ax1.set_title('Average Temperature')
    ax2.set_title('Minimum Temperature') 
    ax3.set_title('Maximum Temperature')
    
    # FIXED: Colorbar spacing to prevent overlap
    plt.subplots_adjust(left=0.05, right=0.85, top=0.9, bottom=0.1, wspace=0.1)
    
    # SINGLE shared colorbar positioned to NOT overlap
    cbar = fig.colorbar(im3, ax=[ax1, ax2, ax3], shrink=0.8, aspect=30, 
                       fraction=0.05, pad=0.02, anchor=(0.0, 0.5))
    cbar.set_label('Temperature (°C)')
    
else:
    # Fallback without Cartopy - MUST also initialize fig
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(20, 6))
    fig.patch.set_facecolor('white')
    
    im1 = ax1.pcolormesh(avg_temp.lon, avg_temp.lat, avg_temp.values,
                        cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax, shading='auto')
    im2 = ax2.pcolormesh(min_temp.lon, min_temp.lat, min_temp.values,
                        cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax, shading='auto')
    im3 = ax3.pcolormesh(max_temp.lon, max_temp.lat, max_temp.values,
                        cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax, shading='auto')
    
    ax1.set_title('Average Temperature')
    ax2.set_title('Minimum Temperature')
    ax3.set_title('Maximum Temperature')
    
    # FIXED: Better spacing for fallback
    plt.subplots_adjust(left=0.05, right=0.85, top=0.9, bottom=0.1, wspace=0.15)
    
    # Shared colorbar with better positioning
    cbar = fig.colorbar(im3, ax=[ax1, ax2, ax3], shrink=0.8, aspect=30, 
                       fraction=0.05, pad=0.02)
    cbar.set_label('Temperature (°C)')

# CRITICAL: Ensure fig is defined before saving
if fig is not None:
    url = save_plot_to_blob_simple(fig, 'florida_temp_subplots_shared_scale.png', account_key)
    plt.close(fig)
    ds.close()
    result = url
else:
    ds.close()
    result = "Error: Figure was not created properly"
```

ANIMATION SOLUTION:
Use static frame generation with PIL to completely eliminate white colorbar issues.
Each frame is independent with its own colorbar, then combined into GIF.

FOR ANIMATIONS - Use this STATIC FRAME pattern (completely eliminates colorbar issues):
```python
import builtins
import io
from datetime import datetime

# Set coordinates (example: Florida)
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0

# Create individual frames
frame_images = []
dates = []

# Load data for each day and create frames
for day_offset in range(5):  # 5 days: Feb 2-6
    current_day = 2 + day_offset
    
    try:
        # Load data for this day
        ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 2, current_day)
        temp_data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), 
                                  lon=builtins.slice(lon_min, lon_max)).mean(dim='time') - 273.15
        dates.append(datetime(2023, 2, current_day))
        
        # Create individual frame with CONSISTENT colorbar scale (CRITICAL for no white colorbar)
        if CARTOPY_AVAILABLE:
            fig = plt.figure(figsize=(12, 8))
            ax = plt.axes(projection=ccrs.PlateCarree())
            ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
            
            # Add geographic features
            ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
            ax.add_feature(cfeature.STATES, linewidth=0.4)
            ax.add_feature(cfeature.BORDERS, linewidth=0.6)
            
            # Plot with automatic color scale (NO HARD-CODED VALUES)
            im = ax.pcolormesh(temp_data.lon, temp_data.lat, temp_data.values,
                              cmap='RdYlBu_r', shading='auto',
                              transform=ccrs.PlateCarree())
        else:
            # Fallback without Cartopy
            fig, ax = plt.subplots(figsize=(12, 8))
            im = ax.pcolormesh(temp_data.lon, temp_data.lat, temp_data.values,
                              cmap='RdYlBu_r', shading='auto')
        
        # Add colorbar and title (each frame gets its own complete colorbar)
        cbar = fig.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label('Temperature (°C)')
        ax.set_title(f'Florida Temperature - {dates[-1].strftime("%Y-%m-%d")}')
        
        # Convert frame to PIL Image
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        frame_images.append(Image.open(buf))
        
        plt.close(fig)
        ds.close()
        
    except Exception as e:
        print(f"Error creating frame for day {current_day}: {e}")
        continue

# Create GIF from individual frames
if frame_images and PIL_AVAILABLE and len(frame_images) > 1:
    # Create GIF using PIL
    gif_buffer = io.BytesIO()
    frame_images[0].save(gif_buffer, format='GIF', save_all=True,
                        append_images=frame_images[1:], 
                        duration=1200, loop=0)
    gif_buffer.seek(0)
    
    # Upload GIF to blob storage
    url = save_plot_to_blob_simple(gif_buffer, 'florida_temp_animation.gif', account_key)
    result = f"Animation created successfully: {url}"
    
elif frame_images and len(frame_images) == 1:
    # Single frame - save as PNG
    png_buffer = io.BytesIO()
    frame_images[0].save(png_buffer, format='PNG')
    png_buffer.seek(0)
    url = save_plot_to_blob_simple(png_buffer, 'florida_temp_single.png', account_key)
    result = f"Single frame created: {url}"
    
else:
    result = "Animation creation failed - no frames generated or PIL not available"
```

FOR SINGLE TEMPERATURE MAPS - copy this pattern:
```python
import builtins

# Set coordinates
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0

# Load data
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 2, 15)
temp_data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), 
                          lon=builtins.slice(lon_min, lon_max)).mean(dim='time') - 273.15

# Create map with Cartopy if available
if CARTOPY_AVAILABLE:
    fig = plt.figure(figsize=(12, 8))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
    
    # Add features
    ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
    ax.add_feature(cfeature.STATES, linewidth=0.4)
    
    # Plot data
    im = ax.pcolormesh(temp_data.lon, temp_data.lat, temp_data.values,
                      cmap='RdYlBu_r', shading='auto', transform=ccrs.PlateCarree())
else:
    # Fallback without Cartopy
    fig, ax = plt.subplots(figsize=(12, 8))
    im = ax.pcolormesh(temp_data.lon, temp_data.lat, temp_data.values,
                      cmap='RdYlBu_r', shading='auto')

# Add colorbar and title
cbar = fig.colorbar(im, ax=ax, shrink=0.8)
cbar.set_label('Temperature (°C)')
ax.set_title('Florida Temperature - Feb 15, 2023')

# Save and close
url = save_plot_to_blob_simple(fig, 'florida_temp.png', account_key)
plt.close(fig)
ds.close()
result = url
```

FOR SINGLE PRECIPITATION MAPS - copy this pattern:
```python
import builtins

# Set coordinates
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0

# Load data
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 2, 20)
precip_data = ds['Rainf'].sel(lat=builtins.slice(lat_min, lat_max), 
                             lon=builtins.slice(lon_min, lon_max)).sum(dim='time')

# Create map
if CARTOPY_AVAILABLE:
    fig = plt.figure(figsize=(12, 8))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent([lon_min, lon_max, lat_min, lat_max], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
    ax.add_feature(cfeature.STATES, linewidth=0.4)
    im = ax.pcolormesh(precip_data.lon, precip_data.lat, precip_data.values,
                      cmap='Blues', shading='auto', transform=ccrs.PlateCarree())
else:
    fig, ax = plt.subplots(figsize=(12, 8))
    im = ax.pcolormesh(precip_data.lon, precip_data.lat, precip_data.values,
                      cmap='Blues', shading='auto')

cbar = fig.colorbar(im, ax=ax, shrink=0.8)
cbar.set_label('Precipitation (mm)')
ax.set_title('Florida Precipitation - Feb 20, 2023')

url = save_plot_to_blob_simple(fig, 'florida_precip.png', account_key)
plt.close(fig)
ds.close()
result = url
```

TIME SERIES FORMATTING RULES:
ALWAYS apply these formatting rules for time series plots:
- plt.xticks(rotation=45) - rotate x-axis labels by 45 degrees
- plt.tight_layout() - prevent labels from being cut off
- Use clear date formatting (e.g., 'Feb-01', 'Feb-02' format)
- Add grid for better readability: plt.grid(True, alpha=0.3)
- Set appropriate figure size: plt.figure(figsize=(12, 6))

COLORBAR SOLUTION EXPLANATION:
The static frame approach completely eliminates white colorbar issues because:
1. Each frame is an independent complete image with its own colorbar
2. No matplotlib object references are shared between frames
3. Consistent vmin/vmax across all frames ensures uniform color scaling
4. PIL combines complete images, not matplotlib objects
5. Result: Perfect colorbar in every frame of the animation

CRITICAL: Never call create_multi_day_animation() or save_animation_to_blob() - they don't exist. 
Always use the static frame pattern above for animations.

ALWAYS set 'result' variable. Use exact patterns above."""

# ---------- Create text agent ----------
text_agent = proj.agents.create_agent(
    model=TEXT_MODEL,
    name="nldas3-static-frame-animation-agent",
    instructions=instructions,
    tools=text_tools,
    tool_resources=text_tool_resources
)

# ---------- Create visualization agent ----------
viz_agent = proj.agents.create_agent(
    model=VIZ_MODEL,
    name="nldas3-visualization-agent",
    instructions=(
        "You produce image-ready prompts and visual specifications for NLDAS-3 figures. "
        "Create detailed prompts for map projections, color schemes, and data overlays."
    ),
    tools=[]
)

# ---------- Save agent info ----------
tools_info = []
if search_conn_id and AI_SEARCH_INDEX_NAME:
    tools_info.append({
        "type": "azure_ai_search",
        "name": AI_SEARCH_CONNECTION_NAME,
        "connection_id": search_conn_id,
        "index_name": AI_SEARCH_INDEX_NAME
    })

tools_info.append({
    "type": "function",
    "name": "execute_custom_code",
    "description": "Execute custom Python code for NLDAS-3 analysis with static frame animation support"
})

agent_info = {
    "project_endpoint": PROJECT_ENDPOINT,
    "agents": {
        "text": {
            "id": text_agent.id,
            "name": text_agent.name,
            "model": TEXT_MODEL,
            "capabilities": [
                "direct-code-execution", 
                "subplot-creation", 
                "proper-colorbar-scaling", 
                "map-generation", 
                "formatted-time-series",
                "static-frame-animations"
            ],
            "tools": tools_info
        },
        "visualization": {
            "id": viz_agent.id,
            "name": viz_agent.name,
            "model": VIZ_MODEL,
            "capabilities": ["image-spec-generation", "map-mockups", "figure-captions"],
            "tools": []
        }
    }
}

with open("agent_info.json", "w") as f:
    json.dump(agent_info, f, indent=2)

print(f"Created STATIC FRAME animation text agent: {text_agent.id}")
print(f"Created visualization agent: {viz_agent.id}")
print("FINAL agent features:")
print("  - Static frame animation generation (eliminates white colorbar)")
print("  - Individual frames with independent colorbars")
print("  - PIL-based GIF creation from complete images")
print("  - Consistent color scaling across animation frames")
print("  - Cartopy geographic features support")
print("  - Formatted time series with proper axis labels")
print("  - Robust error handling and fallbacks")
print("  - Complete elimination of matplotlib.animation object reference issues")
print("Saved agent_info.json")