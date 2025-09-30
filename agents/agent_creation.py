# create agent_info.json - FINAL VERSION with Proper Colorbar Scaling AND Time Series Formatting

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

# ---------- ULTRA-SIMPLE INSTRUCTIONS WITH PROPER COLORBAR SCALING AND TIME SERIES FORMATTING ----------
instructions = """MANDATORY: Call execute_custom_code immediately.

🚨 CRITICAL: Use ccrs.PlateCarree() object, NEVER use 'platecarree' string for projections.

CRITICAL: ONLY use these exact function names (no others exist):
- load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
- create_multi_day_animation(year, month, day, num_days, 'Tair', lat_min, lat_max, lon_min, lon_max, 'Region')
- save_animation_to_blob(anim, filename, account_key)
- save_plot_to_blob_simple(fig, filename, account_key)
- create_cartopy_map(lon, lat, data, title, label, cmap)

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

TIME SERIES FORMATTING RULES:
ALWAYS apply these formatting rules for any time series plot:
- plt.xticks(rotation=45) - rotate x-axis labels by 45 degrees
- plt.tight_layout() - prevent labels from being cut off
- Use clear date formatting (e.g., 'Feb-01', 'Feb-02' format)
- Add grid for better readability: plt.grid(True, alpha=0.3)
- Set appropriate figure size: plt.figure(figsize=(12, 6))

FOR TIME SERIES PLOTS - copy this pattern:
```python
import builtins
import matplotlib.pyplot as plt
import pandas as pd

# Florida coordinates
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0

# Load multiple days and calculate statistics
dates = []
avg_temps = []
min_temps = []
max_temps = []

for day in range(1, 11):  # Feb 1-10
    try:
        ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 2, day)
        temp_data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)) - 273.15
        
        # Calculate daily statistics
        daily_avg = float(temp_data.mean())
        daily_min = float(temp_data.min()) 
        daily_max = float(temp_data.max())
        
        dates.append(f"2023-02-{day:02d}")
        avg_temps.append(daily_avg)
        min_temps.append(daily_min)
        max_temps.append(daily_max)
        
        ds.close()
    except Exception as e:
        print(f"Error loading day {day}: {e}")
        continue

# Create time series plot with proper formatting
plt.figure(figsize=(12, 6))
plt.plot(dates, avg_temps, 'o-', label='Average Temperature (°C)', linewidth=2, markersize=6)
plt.plot(dates, min_temps, 's-', label='Minimum Temperature (°C)', linewidth=2, markersize=6)
plt.plot(dates, max_temps, '^-', label='Maximum Temperature (°C)', linewidth=2, markersize=6)

plt.title('Florida Temperature Time Series: Feb 1-10, 2023', fontsize=14, fontweight='bold')
plt.xlabel('Date', fontsize=12)
plt.ylabel('Temperature (°C)', fontsize=12)
plt.legend(fontsize=11)
plt.grid(True, alpha=0.3)

# CRITICAL: Apply proper x-axis formatting
plt.xticks(rotation=45)
plt.tight_layout()

url = save_plot_to_blob_simple(plt.gcf(), 'florida_temp_timeseries.png', account_key)
plt.close()
result = url
```

FOR SUBPLOT REQUESTS (multiple variables or dates) - copy this pattern:
```python
import builtins
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 1)
temp_data = ds['Tair'].sel(lat=builtins.slice(37.9, 39.7), lon=builtins.slice(-79.5, -75.0)) - 273.15

avg_temp = temp_data.mean(dim='time')
min_temp = temp_data.min(dim='time') 
max_temp = temp_data.max(dim='time')

shared_vmin, shared_vmax = float(min(avg_temp.min(), min_temp.min(), max_temp.min())), float(max(avg_temp.max(), min_temp.max(), max_temp.max()))

fig = plt.figure(figsize=(20, 6))
ax1 = fig.add_subplot(1, 3, 1, projection=ccrs.PlateCarree())
ax2 = fig.add_subplot(1, 3, 2, projection=ccrs.PlateCarree())
ax3 = fig.add_subplot(1, 3, 3, projection=ccrs.PlateCarree())

for ax in [ax1, ax2, ax3]:
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.STATES)
    gl = ax.gridlines(draw_labels=True, alpha=0.3)

im1 = ax1.pcolormesh(avg_temp.lon, avg_temp.lat, avg_temp.values, cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax, shading='auto', transform=ccrs.PlateCarree())
ax1.set_title('Average Temperature')

im2 = ax2.pcolormesh(min_temp.lon, min_temp.lat, min_temp.values, cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax, shading='auto', transform=ccrs.PlateCarree())
ax2.set_title('Minimum Temperature')

im3 = ax3.pcolormesh(max_temp.lon, max_temp.lat, max_temp.values, cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax, shading='auto', transform=ccrs.PlateCarree())
ax3.set_title('Maximum Temperature')

plt.subplots_adjust(left=0.05, right=0.85, wspace=0.1)
plt.colorbar(im3, ax=[ax1, ax2, ax3], shrink=0.8, pad=0.02, label='Temperature (°C)')
url = save_plot_to_blob_simple(fig, 'subplot.png', account_key)
plt.close(fig)
ds.close()
result = url
```

FOR SINGLE PRECIPITATION MAPS - copy this pattern:
```python
import builtins
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 21)
data = ds['Rainf'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).sum(dim='time')
fig, ax = create_cartopy_map(data.lon, data.lat, data.values, 'Florida Precipitation', 'Precipitation (mm)', 'Blues')
url = save_plot_to_blob_simple(fig, 'florida_precip.png', account_key)
plt.close(fig)
ds.close()
result = url
```

FOR SINGLE TEMPERATURE MAPS - copy this pattern:
```python
import builtins
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 15)
data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).mean(dim='time') - 273.15
fig, ax = create_cartopy_map(data.lon, data.lat, data.values, 'Florida Temperature', 'Temperature (°C)', 'RdYlBu_r')
url = save_plot_to_blob_simple(fig, 'florida_temp.png', account_key)
plt.close(fig)
ds.close()
result = url
```

FOR ANIMATIONS - copy this pattern:
```python
import builtins
import matplotlib.animation as animation

# Set coordinates
lat_min, lat_max = 37.9, 39.7
lon_min, lon_max = -79.5, -75.0

try:
    anim, fig = create_multi_day_animation(2023, 1, 1, 5, 'Tair', lat_min, lat_max, lon_min, lon_max, 'Maryland')
    url = save_animation_to_blob(anim, 'maryland_temp_jan1-5.gif', account_key)
    plt.close(fig)
    result = url
    
except Exception as e:
    print(f"Animation failed: {e}")
    ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)
    data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).mean(dim='time') - 273.15
    fig, ax = create_cartopy_map(data.lon, data.lat, data.values, 'Maryland Temperature', 'Temperature (°C)', 'RdYlBu_r')
    url = save_plot_to_blob_simple(fig, 'maryland_temp_fallback.png', account_key)
    plt.close(fig)
    ds.close()
    result = f"Animation failed, showing static map: {url}"
```

OPTIONAL CITY LABELS (no gray fill):
To include city names on a map add: region_name='Florida' (or 'Maryland','California','Michigan','Alaska') and show_cities=True
Example:
```python
import builtins
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 9, 30)
data = ds['Tair'].sel(lat=builtins.slice(37.9, 39.7), lon=builtins.slice(-79.5, -75.0)).mean(dim='time') - 273.15
fig, ax = create_cartopy_map(data.lon, data.lat, data.values,
                             'Maryland Temperature with Cities',
                             'Temperature (°C)', 'RdYlBu_r',
                             region_name='maryland', show_cities=True)
url = save_plot_to_blob_simple(fig, 'maryland_temp_cities.png', account_key)
plt.close(fig); ds.close(); result = url
```
If user explicitly asks for city names or labels, use show_cities=True.

ALWAYS set 'result' variable. Use exact patterns above."""

# ---------- Create text agent with proper colorbar scaling and time series formatting ----------
text_agent = proj.agents.create_agent(
    model=TEXT_MODEL,
    name="nldas3-final-agent-with-formatted-timeseries",
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
    "description": "Execute custom Python code for NLDAS-3 analysis with proper formatting"
})

agent_info = {
    "project_endpoint": PROJECT_ENDPOINT,
    "agents": {
        "text": {
            "id": text_agent.id,
            "name": text_agent.name,
            "model": TEXT_MODEL,
            "capabilities": ["direct-code-execution", "subplot-creation", "proper-colorbar-scaling", "map-generation", "formatted-time-series"],
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

print(f"Created FINAL text agent with formatted time series: {text_agent.id}")
print(f"Created visualization agent: {viz_agent.id}")
print("FINAL agent features:")
print("  - Proper colorbar scaling for meaningful comparisons")
print("  - Shared color scales for same variables across time/space")
print("  - Separate optimized scales for different variables")
print("  - Subplot pattern included to prevent timeouts")
print("  - Clean shared colorbar layout")
print("  - FORMATTED TIME SERIES with rotated x-axis labels")
print("  - Grid lines and proper figure sizing for time series")
print("Saved agent_info.json")