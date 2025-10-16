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

🚨 CRITICAL: NEVER override ACCOUNT_NAME or account_key variables - they are pre-configured.

CRITICAL: ONLY use these exact function names (no others exist):
- load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
- load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, month)
- create_multi_day_animation(year, month, day, num_days, 'Tair', lat_min, lat_max, lon_min, lon_max, 'Region')
- save_animation_to_blob(anim, filename, account_key)
- save_plot_to_blob_simple(fig, filename, account_key)
- create_cartopy_map(lon, lat, data, title, colorbar_label, cmap)
- create_geotiff_overlay(data.values, data.lon, data.lat, 'filename.tif', account_key)

# Extract location from user request dynamically
user_query_lower = user_request.lower()

# Dynamic coordinate detection based on user query
if 'maryland' in user_query_lower:
    lat_min, lat_max = 38.8, 39.8
    lon_min, lon_max = -79.5, -75.0
    region_name = 'Maryland'
elif 'florida' in user_query_lower:
    lat_min, lat_max = 24.5, 31.0
    lon_min, lon_max = -87.6, -80.0
    region_name = 'Florida'
elif 'california' in user_query_lower:
    lat_min, lat_max = 32.5, 42.0
    lon_min, lon_max = -124.4, -114.1
    region_name = 'California'
elif 'texas' in user_query_lower:
    lat_min, lat_max = 25.8, 36.5
    lon_min, lon_max = -106.6, -93.5
    region_name = 'Texas'
elif 'mexico' in user_query_lower:
    lat_min, lat_max = 14.5, 32.7
    lon_min, lon_max = -118.4, -86.7
    region_name = 'Mexico'
else:
    # Default to Maryland if no region detected
    lat_min, lat_max = 38.8, 39.8
    lon_min, lon_max = -79.5, -75.0
    region_name = 'Maryland'

# Extract year and month from user request
import re
year_match = re.search(r'(20\d{2})', user_request)
year = int(year_match.group(1)) if year_match else 2020

month_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)', user_request.lower())
month_names = ['january','february','march','april','may','june','july','august','september','october','november','december']
month = month_names.index(month_match.group(1)) + 1 if month_match else 5

# Load SPI data
ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, month)
data = ds['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(data, 'squeeze'):
    data = data.squeeze()

# FIXED: For TEXT queries (what is, average, how much, tell me) - NOT show me
if any(phrase in user_request.lower() for phrase in ['what is', 'average', 'how much', 'tell me']):
    spi_value = float(data.mean())
    ds.close()
    
    if spi_value <= -2.0:
        condition = "extreme drought"
    elif spi_value <= -1.5:
        condition = "severe drought"
    elif spi_value <= -1.0:
        condition = "moderate drought"
    elif spi_value <= -0.5:
        condition = "mild drought"
    elif spi_value <= 0.5:
        condition = "near normal"
    elif spi_value <= 1.0:
        condition = "mild wet"
    elif spi_value <= 1.5:
        condition = "moderate wet"
    elif spi_value <= 2.0:
        condition = "severe wet"
    else:
        condition = "extreme wet"
    
    result = f"The SPI in {region_name} for {month_names[month-1].title()} {year} is {spi_value:.2f} ({condition})"

# FIXED: For MAP queries (show me, display, visualize) - return map
else:
    title = f"Standardized Precipitation Index (SPI) — {month_names[month-1].title()} {year}, {region_name}"
    fig, ax = create_spi_map_with_categories(data.longitude, data.latitude, data.values, title, region_name=region_name.lower())
    url = save_plot_to_blob_simple(fig, f'{region_name.lower()}_spi_{year}_{month:02d}.png', account_key)
    plt.close(fig)
    ds.close()
    result = url

FOR SPI MULTI-YEAR ANIMATION (show drought trends over time):
```python
import builtins
# Create SPI animation showing May conditions from 2010-2020 in California
lat_min, lat_max = 32.0, 42.0  # California
lon_min, lon_max = -125.0, -114.0

try:
    anim, fig = create_spi_multi_year_animation(2010, 2020, 5, lat_min, lat_max, lon_min, lon_max, 'California')
    url = save_animation_to_blob(anim, 'california_may_spi_2010_2020.gif', account_key)
    plt.close(fig)
    result = url
    
except Exception as e:
    print(f"SPI animation failed: {e}")
    # Fallback to single year SPI map
    ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2020, 5)
    data = ds['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
    if hasattr(data, 'squeeze'):
        data = data.squeeze()
    fig, ax = create_spi_map_with_categories(data.longitude, data.latitude, data.values, 'California SPI - May 2020', region_name='california')
    url = save_plot_to_blob_simple(fig, 'california_may_2020_spi.png', account_key)
    plt.close(fig)
    ds.close()
    result = f"Multi-year animation failed, showing May 2020: {url}"
```

FOR SPI MONTHLY COMPARISON (instead of animation):
```python
import builtins
# Compare SPI between two months - Florida May vs June 2023
lat_min, lat_max = 24.5, 31.0  # Florida
lon_min, lon_max = -87.6, -80.0

# Load May 2023 SPI
ds_may, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2023, 5)
may_data = ds_may['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(may_data, 'squeeze'):
    may_data = may_data.squeeze()

# Load June 2023 SPI  
ds_june, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2023, 6)
june_data = ds_june['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(june_data, 'squeeze'):
    june_data = june_data.squeeze()

# Create subplot comparison with increased height for note
fig = plt.figure(figsize=(20, 12))
ax1 = fig.add_subplot(1, 2, 1, projection=ccrs.PlateCarree())
ax2 = fig.add_subplot(1, 2, 2, projection=ccrs.PlateCarree())

# Both use same SPI scale (-2.5 to 2.5) with RdBu colormap (original for subplots)
im1 = ax1.pcolormesh(may_data.longitude, may_data.latitude, may_data.values, cmap='RdBu', vmin=-2.5, vmax=2.5, shading='auto', transform=ccrs.PlateCarree())
ax1.add_feature(cfeature.COASTLINE)
ax1.add_feature(cfeature.STATES)
ax1.set_title('Florida SPI - May 2023')

im2 = ax2.pcolormesh(june_data.longitude, june_data.latitude, june_data.values, cmap='RdBu', vmin=-2.5, vmax=2.5, shading='auto', transform=ccrs.PlateCarree())
ax2.add_feature(cfeature.COASTLINE)
ax2.add_feature(cfeature.STATES)  
ax2.set_title('Florida SPI - June 2023')

plt.subplots_adjust(left=0.05, right=0.85, wspace=0.1, bottom=0.12)
cbar = plt.colorbar(im2, ax=[ax1, ax2], shrink=0.8, pad=0.02, label='SPI3 (Drought Index)')

# NEW: Add SPI category explanation at bottom of subplot
note_text = ("SPI Categories: Extreme Drought (≤ -2.0, Red) • Severe Drought (-2.0 to -1.5) • " +
           "Moderate Drought (-1.5 to -1.0) • Mild Drought (-1.0 to -0.5) • " +
           "Near Normal (-0.5 to 0.5, White) • Mild Wet (0.5 to 1.0) • " +
           "Moderate Wet (1.0 to 1.5) • Severe Wet (1.5 to 2.0) • Extreme Wet (≥ 2.0, Blue)")

fig.text(0.5, 0.02, note_text, ha='center', va='bottom', fontsize=16, 
        fontweight='bold', wrap=True, bbox=dict(boxstyle='round,pad=0.5', 
        facecolor='lightgray', alpha=0.8))

url = save_plot_to_blob_simple(fig, 'florida_spi_may_june_2023.png', account_key)
plt.close(fig)
ds_may.close()
ds_june.close()
result = url
```

FOR TIME SERIES PLOTS - copy this pattern:
```python
import builtins
import matplotlib.pyplot as plt
import pandas as pd

# Example coordinates (replace with requested region)
lat_min, lat_max = 24.5, 31.0  # Example: Florida
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

plt.title('Temperature Time Series: Feb 1-10, 2023', fontsize=14, fontweight='bold')
plt.xlabel('Date', fontsize=12)
plt.ylabel('Temperature (°C)', fontsize=12)
plt.legend(fontsize=11)
plt.grid(True, alpha=0.3)

# CRITICAL: Apply proper x-axis formatting
plt.xticks(rotation=45)
plt.tight_layout()

url = save_plot_to_blob_simple(plt.gcf(), 'temp_timeseries.png', account_key)
plt.close()
result = url
```

FOR SUBPLOT REQUESTS (multiple variables or dates) - copy this pattern:
```python
import builtins
# Load data for BOTH regions first to calculate shared color scale
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 3, 15)  # March 15, 2023

# Florida data
florida_data = ds['Tair'].sel(lat=builtins.slice(24.5, 31.0), lon=builtins.slice(-87.6, -80.0)).mean(dim='time') - 273.15

# Maryland data  
maryland_data = ds['Tair'].sel(lat=builtins.slice(37.9, 39.7), lon=builtins.slice(-79.5, -75.0)).mean(dim='time') - 273.15

# CRITICAL: Calculate shared color scale from BOTH datasets
shared_vmin = float(min(florida_data.min(), maryland_data.min()))
shared_vmax = float(max(florida_data.max(), maryland_data.max()))

fig = plt.figure(figsize=(20, 8))
ax1 = fig.add_subplot(1, 2, 1, projection=ccrs.PlateCarree())
ax2 = fig.add_subplot(1, 2, 2, projection=ccrs.PlateCarree())

for ax in [ax1, ax2]:
    ax.add_feature(cfeature.COASTLINE)
    ax.add_feature(cfeature.STATES)
    ax.set_xticks([])
    ax.set_yticks([])

# BOTH plots use the SAME shared color scale
im1 = ax1.pcolormesh(florida_data.lon, florida_data.lat, florida_data.values, cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax, shading='auto', transform=ccrs.PlateCarree())
ax1.set_title('Florida Average Temperature')

im2 = ax2.pcolormesh(maryland_data.lon, maryland_data.lat, maryland_data.values, cmap='RdYlBu_r', vmin=shared_vmin, vmax=shared_vmax, shading='auto', transform=ccrs.PlateCarree())
ax2.set_title('Maryland Average Temperature')

plt.subplots_adjust(left=0.05, right=0.85, wspace=0.1)
# Single shared colorbar for both plots
cbar = plt.colorbar(im2, ax=[ax1, ax2], shrink=0.8, pad=0.02, label='Temperature (°C)')
url = save_plot_to_blob_simple(fig, 'subplot_florida_maryland_temp.png', account_key)
plt.close(fig)
ds.close()
result = url
```

FOR SINGLE PRECIPITATION MAPS - copy this pattern:
```python
import builtins, json, numpy as np, time
# Use coordinates for requested region
lat_min, lat_max = 24.5, 31.0  # Example: Florida
lon_min, lon_max = -87.6, -80.0
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 21)
data = ds['Rainf'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).sum(dim='time')

# Create GeoTIFF overlay
timestamp = int(time.time())
geotiff_filename = f'precip_overlay_{timestamp}.tif'
geotiff_url = create_geotiff_overlay(data.values, data.lon, data.lat, geotiff_filename, account_key)

# Create static map
fig, ax = create_cartopy_map(data.lon, data.lat, data.values, 'Precipitation', 'Precipitation (mm)', 'Blues')
static_filename = f'precip_static_{timestamp}.png'
static_url = save_plot_to_blob_simple(fig, static_filename, account_key)

# Build GeoJSON and response
geo_features = []
lon_vals = data.lon.values
lat_vals = data.lat.values
vals = data.values
for i in range(0, len(lat_vals), max(1, len(lat_vals)//25 or 1)):
    for j in range(0, len(lon_vals), max(1, len(lon_vals)//25 or 1)):
        v = float(vals[i, j])
        if np.isfinite(v):
            geo_features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon_vals[j]), float(lat_vals[i])]},
                "properties": {"value": v, "variable": "precipitation", "unit": "mm"}
            })
geojson = {"type": "FeatureCollection", "features": geo_features}
center_lon = float((lon_min + lon_max)/2)
center_lat = float((lat_min + lat_max)/2)
bounds = {"north": float(lat_max), "south": float(lat_min), "east": float(lon_max), "west": float(lon_min)}
map_config = {"center": [center_lon, center_lat], "zoom": 6, "style": "satellite", "overlay_mode": True}
plt.close(fig); ds.close()
result = {
    "static_url": static_url,
    "geotiff_url": geotiff_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config
}
```

FOR SINGLE TEMPERATURE MAPS - copy this pattern (WITH GeoTIFF):
```python
import builtins, json, numpy as np, time
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 15)
data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).mean(dim='time') - 273.15

# Create GeoTIFF overlay
timestamp = int(time.time())
geotiff_filename = f'temp_overlay_{timestamp}.tif'
geotiff_url = create_geotiff_overlay(data.values, data.lon, data.lat, geotiff_filename, account_key)

# Create static map
fig, ax = create_cartopy_map(data.lon, data.lat, data.values, 'Temperature', 'Temperature (°C)', 'RdYlBu_r')
static_filename = f'temp_static_{timestamp}.png'
static_url = save_plot_to_blob_simple(fig, static_filename, account_key)

# Build GeoJSON and response
geo_features = []
lon_vals = data.lon.values
lat_vals = data.lat.values
vals = data.values
for i in range(0, len(lat_vals), max(1, len(lat_vals)//25 or 1)):
    for j in range(0, len(lon_vals), max(1, len(lon_vals)//25 or 1)):
        v = float(vals[i, j])
        if np.isfinite(v):
            geo_features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon_vals[j]), float(lat_vals[i])]},
                "properties": {"value": v, "variable": "temperature", "unit": "°C"}
            })
geojson = {"type": "FeatureCollection", "features": geo_features}
center_lon = float((lon_min + lon_max)/2)
center_lat = float((lat_min + lat_max)/2)
bounds = {"north": float(lat_max), "south": float(lat_min), "east": float(lon_max), "west": float(lon_min)}
map_config = {"center": [center_lon, center_lat], "zoom": 6, "style": "satellite", "overlay_mode": True}

plt.close(fig); ds.close()
result = {
    "static_url": static_url,
    "geotiff_url": geotiff_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config
}
```

FOR ANIMATIONS - copy this pattern:
```python
import builtins
import matplotlib.animation as animation

# Set coordinates
lat_min, lat_max = 37.9, 39.7
lon_min, lon_max = -79.5, -75.0

try:
    anim, fig = create_multi_day_animation(2023, 1, 1, 5, 'Tair', lat_min, lat_max, lon_min, lon_max, 'Region')
    url = save_animation_to_blob(anim, 'temp_jan1-5.gif', account_key)
    plt.close(fig)
    result = url
    
except Exception as e:
    print(f"Animation failed: {e}")
    ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)
    data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).mean(dim='time') - 273.15
    fig, ax = create_cartopy_map(data.lon, data.lat, data.values, 'Temperature', 'Temperature (°C)', 'RdYlBu_r')
    url = save_plot_to_blob_simple(fig, 'temp_fallback.png', account_key)
    plt.close(fig)
    ds.close()
    result = f"Animation failed, showing static map: {url}"
```

FOR SPI MAPS (WITH GeoTIFF):
```python
import builtins, json, numpy as np, time
lat_min, lat_max = 32.0, 42.0
lon_min, lon_max = -125.0, -114.0
ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2020, 5)
data = ds['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(data, 'squeeze'): data = data.squeeze()

# Create GeoTIFF overlay
timestamp = int(time.time())
geotiff_filename = f'spi_overlay_{timestamp}.tif'
geotiff_url = create_geotiff_overlay(data.values, data.longitude, data.latitude, geotiff_filename, account_key)

# Create static map
fig, ax = create_spi_map_with_categories(data.longitude, data.latitude, data.values,
                                         'California SPI - May 2020', region_name='california')
static_filename = f'spi_static_{timestamp}.png'
static_url = save_plot_to_blob_simple(fig, static_filename, account_key)

# Build GeoJSON and response
geo_features = []
lon_vals = data.longitude.values
lat_vals = data.latitude.values
vals = data.values
for i in range(0, len(lat_vals), max(1, len(lat_vals)//25 or 1)):
    for j in range(0, len(lon_vals), max(1, len(lon_vals)//25 or 1)):
        v = float(vals[i, j])
        if np.isfinite(v):
            geo_features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon_vals[j]), float(lat_vals[i])]},
                "properties": {"spi": v}
            })
geojson = {"type": "FeatureCollection", "features": geo_features}
center_lon = float((lon_min + lon_max)/2)
center_lat = float((lat_min + lat_max)/2)
bounds = {"north": float(lat_max), "south": float(lat_min), "east": float(lon_max), "west": float(lon_min)}
map_config = {"center": [center_lon, center_lat], "zoom": 5, "style": "satellite", "overlay_mode": True}
plt.close(fig); ds.close()
result = {
    "static_url": static_url,
    "geotiff_url": geotiff_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config
}
```

🚨 UPDATED RULE:
FOR ANY MAP RESULT you MUST return a dict with:
- static_url (annotated figure with legend/colorbar) - REQUIRED
- geotiff_url (georeferenced GeoTIFF for Azure Maps) - REQUIRED
- geojson - REQUIRED
- bounds (north,south,east,west) - REQUIRED  
- map_config {center, zoom, style, overlay_mode} - REQUIRED

Both static_url and geotiff_url must be different files. Use timestamps to make filenames unique.

# ...existing remaining instructions unchanged...
"""

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