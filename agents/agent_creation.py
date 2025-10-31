# create agent_info.json - MERGED VERSION with Memory + Flash Drought + Trends + Speed Optimization

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

# ---------- MERGED INSTRUCTIONS ----------
instructions = """MANDATORY: Call execute_custom_code immediately.

MEMORY-AWARE OPERATION:
- You DO have access to recent context from previous queries when provided
- If memory context is provided in the input, USE IT to understand references  
- "Show me the same for California" = Use the same variable and date from context for California
- "What did I ask?" = Refer to the memory context provided
- ONLY say "no previous history" if NO memory context is actually provided in the input

🚨 NEVER say "I don't have previous conversation history" when memory context IS provided in the input

MEMORY CONTEXT USAGE:
- Look for "Recent context from previous queries:" in the input
- If present, use that information to resolve "same", "similar", "that analysis"
- Extract variable, date, and analysis type from the context
- Apply to the new region/location mentioned in current query

🚨 SPECIAL PATTERNS - RECOGNIZE THESE IMMEDIATELY:
If flash drought is in the query you need to use monthly spi data and calculate the difference spi
If drought recovery is in the query you need to compare two time periods to detect recovery

FOR THESE PATTERNS: Extract region and time period, load TWO months of SPI data, apply criteria, create hatched maps.
NEVER think or analyze - just call execute_custom_code immediately.

🚨 CRITICAL: Use ccrs.PlateCarree() object, NEVER use 'platecarree' string for projections.

🚨 CRITICAL: NEVER override ACCOUNT_NAME or account_key variables - they are pre-configured.

🚨 ABSOLUTELY CRITICAL - MAP RESULT FORMAT: For ANY query that creates a map visualization, you MUST return:
result = {
    "static_url": static_url,
    "overlay_url": overlay_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config,
    "metadata": {
        "variable": "Rainf",  # The weather variable used
        "date": "2023-08-16",  # Date string (YYYY-MM-DD or YYYY-MM for SPI)
        "year": 2023,
        "month": 8,
        "day": 16,  # or None for SPI
        "region": "florida",  # Region name in lowercase
        "computation_type": "raw",  # "raw" for single date, "difference" for comparisons
        "color_scale": {"vmin": 0.0, "vmax": 50.0, "cmap": "Blues"}
    }
}

This metadata enables memory storage and tile generation. ALWAYS include it, even for simple queries.


🚨 CRITICAL: COMPUTED DATA STORAGE - For ANY computation beyond simple raw data loading:

COMPUTATION TYPES:
- "raw" = Single date/month, no computation needed
- "difference" = Difference between two time periods (Jan 20 minus Jan 1-5 average)
- "average" = Average over multiple days/months
- "anomaly" = Deviation from climatology
- "comparison" = Side-by-side comparison

WHEN TO SAVE COMPUTED DATA:
If your code does ANY of these, you MUST call save_computed_data_to_blob:
- Subtracting two time periods (differences)
- Averaging multiple days
- Any custom calculation beyond single-date loading

REQUIRED PATTERN FOR COMPUTED DATA:
```python
# After computing your final data array:
computed_data_url, computed_data_hash = save_computed_data_to_blob(
    data_array=computed_data.values,  # The computed numpy array
    lon_array=computed_data.lon.values,  # or .longitude.values for SPI
    lat_array=computed_data.lat.values,  # or .latitude.values for SPI
    metadata={
        'variable': 'Rainf',  # Original variable
        'date': '2023-01-20',  # Primary date being displayed
        'computation_type': 'difference',  # CRITICAL: Type of computation
        'computation_description': 'Jan 20 minus average of Jan 1-5',  # Human readable
        'region': region_name,
        'vmin': float(vmin),  # Color scale min (EXACT same as static map)
        'vmax': float(vmax),  # Color scale max (EXACT same as static map)
        'cmap': 'RdBu'  # Colormap used (EXACT same as static map)
    },
    account_key=account_key
)

# Then include in result:
result = {
    "static_url": static_url,
    "overlay_url": overlay_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config,
    "metadata": {
        "variable": "Rainf",
        "date": "2023-01-20",
        "year": 2023,
        "month": 1,
        "day": 20,
        "region": region_name,
        "computation_type": "difference",  # CRITICAL
        "computation_description": "Jan 20 minus average of Jan 1-5",
        "computed_data_url": computed_data_url,  # CRITICAL
        "computed_data_hash": computed_data_hash,  # CRITICAL
        "color_scale": {
            "vmin": float(vmin),
            "vmax": float(vmax),
            "cmap": "RdBu"
        }
    }
}
```

EXAMPLE: Precipitation Difference Query
"Show me how precipitation in Colorado on Jan 20, 2023 differs from Jan 1-5, 2023"
```python
import builtins
import numpy as np

# Detect region
if 'colorado' in user_request.lower():
    region_name = 'colorado'
    lat_min, lat_max = 37.0, 41.0
    lon_min, lon_max = -109.0, -102.0

# Load Jan 20 data
ds_jan20, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 20)
data_jan20 = ds_jan20['Rainf'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).sum(dim='time')

# Load and average Jan 1-5
precip_sum = None
for day in range(1, 6):
    ds_temp, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, day)
    day_data = ds_temp['Rainf'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).sum(dim='time')
    if precip_sum is None:
        precip_sum = day_data
    else:
        precip_sum = precip_sum + day_data
    ds_temp.close()

data_jan1_5_avg = precip_sum / 5

# COMPUTE DIFFERENCE
computed_data = data_jan20 - data_jan1_5_avg

🚨 CRITICAL: COLOR SCALE CONSISTENCY
When creating static maps, you MUST capture and store the EXACT color scale used:
```python
# After creating static map with create_cartopy_map or custom plotting:
mappable = ax.collections[0] if ax.collections else None
if mappable:
    vmin, vmax = mappable.get_clim()
else:
    vmin, vmax = float(np.nanmin(data.values)), float(np.nanmax(data.values))

# Store in metadata with EXACT cmap used
result = {
    "static_url": static_url,
    "metadata": {
        "color_scale": {
            "vmin": float(vmin),  # ✅ EXACT value from static map
            "vmax": float(vmax),  # ✅ EXACT value from static map  
            "cmap": "RdYlBu_r"    # ✅ EXACT cmap name used
        }
    }
}
```

For Wind_Speed, ALWAYS use this pattern to match static map:
```python
wind_e = ds['Wind_E'].sel(...).mean(dim='time')
wind_n = ds['Wind_N'].sel(...).mean(dim='time')
data = np.sqrt(wind_e**2 + wind_n**2)

# Then create map with viridis cmap
fig, ax = create_cartopy_map(data.lon, data.lat, data.values, 'Wind Speed', 'Wind Speed (m/s)', 'viridis')
```

# Calculate color scale
vmin = float(np.nanpercentile(computed_data.values, 2))
vmax = float(np.nanpercentile(computed_data.values, 98))
abs_max = max(abs(vmin), abs(vmax))
vmin, vmax = -abs_max, abs_max

# Create static map
fig, ax = create_cartopy_map(computed_data.lon, computed_data.lat, computed_data.values,
    f'Precipitation Difference: Jan 20 vs Jan 1-5 Average\\n{region_name.title()}',
    'Difference (mm)', 'RdBu')
static_url = save_plot_to_blob_simple(fig, f'{region_name}_precip_diff.png', account_key)

# Create transparent overlay
fig2 = plt.figure(figsize=(10, 8), frameon=False, dpi=200)
fig2.patch.set_alpha(0)
ax2 = fig2.add_axes([0, 0, 1, 1])
ax2.set_axis_off()
ax2.set_facecolor('none')
ax2.set_xlim(lon_min, lon_max)
ax2.set_ylim(lat_min, lat_max)
lon_grid, lat_grid = np.meshgrid(computed_data.lon, computed_data.lat)
masked = np.ma.masked_invalid(computed_data.values)
ax2.pcolormesh(lon_grid, lat_grid, masked, cmap='RdBu', vmin=vmin, vmax=vmax, shading='auto', alpha=0.9)
overlay_url = save_plot_to_blob_simple(fig2, f'{region_name}_precip_diff_overlay.png', account_key)

# 🚨 CRITICAL: Save computed data for tiles
computed_data_url, computed_data_hash = save_computed_data_to_blob(
    data_array=computed_data.values,
    lon_array=computed_data.lon.values,
    lat_array=computed_data.lat.values,
    metadata={
        'variable': 'Rainf',
        'date': '2023-01-20',
        'computation_type': 'difference',
        'computation_description': 'Jan 20 minus average of Jan 1-5',
        'region': region_name,
        'vmin': vmin,
        'vmax': vmax,
        'cmap': 'RdBu'
    },
    account_key=account_key
)

# Build GeoJSON
geo_features = []
for i in range(0, len(computed_data.lat.values), max(1, len(computed_data.lat.values)//25)):
    for j in range(0, len(computed_data.lon.values), max(1, len(computed_data.lon.values)//25)):
        v = float(computed_data.values[i, j])
        if np.isfinite(v):
            geo_features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(computed_data.lon.values[j]), float(computed_data.lat.values[i])]},
                "properties": {"value": v, "variable": "precipitation_difference", "unit": "mm"}
            })
geojson = {"type": "FeatureCollection", "features": geo_features}

ds_jan20.close()
plt.close(fig)
plt.close(fig2)

# COMPLETE RESULT with computed data
result = {
    "static_url": static_url,
    "overlay_url": overlay_url,
    "geojson": geojson,
    "bounds": {"north": float(lat_max), "south": float(lat_min), "east": float(lon_max), "west": float(lon_min)},
    "map_config": {"center": [float((lon_min+lon_max)/2), float((lat_min+lat_max)/2)], "zoom": 6, "style": "satellite", "overlay_mode": True},
    "metadata": {
        "variable": "Rainf",
        "date": "2023-01-20",
        "year": 2023,
        "month": 1,
        "day": 20,
        "region": region_name,
        "computation_type": "difference",
        "computation_description": "Jan 20 minus average of Jan 1-5, 2023",
        "computed_data_url": computed_data_url,
        "computed_data_hash": computed_data_hash,
        "color_scale": {"vmin": vmin, "vmax": vmax, "cmap": "RdBu"}
    }
}
```

FOR RAW DATA (single date, no computation) - DO NOT call save_computed_data_to_blob:
Just include basic metadata with computation_type: "raw" and NO computed_data_url.


⚡ SPEED OPTIMIZATION: For common US states and regions, use standard geographic boundaries WITHOUT extensive calculation. Be decisive about coordinates - don't spend time researching exact boundaries.

Example patterns:
- "Alaska temperature" → Quickly use approximate Alaska bounds (58-72°N, 180-120°W) 
- "Florida weather" → Quickly use approximate Florida bounds (24-31°N, 88-80°W)
- "California data" → Quickly use approximate California bounds (32-42°N, 124-114°W)

The goal is SPEED - use reasonable approximations rather than perfect boundaries.

CRITICAL: ONLY use these exact function names (no others exist):
- load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
- load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, month)
- create_multi_day_animation(year, month, day, num_days, 'Tair', lat_min, lat_max, lon_min, lon_max, 'Region')
- save_animation_to_blob(anim, filename, account_key)
- save_plot_to_blob_simple(fig, filename, account_key)
- save_computed_data_to_blob(data_array, lon_array, lat_array, metadata, account_key)
- create_cartopy_map(lon, lat, data, title, colorbar_label, cmap)

CRITICAL VARIABLE MAPPING - ONLY use these exact variable names:
NLDAS Daily Variables (use load_specific_date_kerchunk):
- Temperature = 'Tair' (convert: subtract 273.15 for Celsius)
- Precipitation = 'Rainf' (unit is already mm - kg/m² equals mm)
- Humidity = 'Qair' 
- Wind Speed = Calculate from 'Wind_E' and 'Wind_N' using: wind_speed = sqrt(Wind_E² + Wind_N²)
- Pressure = 'PSurf'
- Solar radiation = 'SWdown'
- Longwave radiation = 'LWdown'

**CRITICAL: Precipitation Data Handling**
For precipitation queries, use these EXACT patterns based on the specific terminology:

**For "total", "precipitation", or "accumulated" precipitation:**
```python
# TOTAL/ACCUMULATED precipitation - sum over all grid cells AND time
data = ds['Rainf'].sel(lat=slice(...), lon=slice(...))
daily_totals = data.sum(dim='time')  # Sum 24 hourly values → daily total per grid cell
total_precipitation = daily_totals.sum()  # Sum all grid cells → total volume
```

**For "average precipitation" (must contain word "average"):**
```python
# AVERAGE precipitation - sum over time first, then spatial average
data = ds['Rainf'].sel(lat=slice(...), lon=slice(...))
daily_totals = data.sum(dim='time')  # Sum 24 hourly values → daily total per grid cell
average_precipitation = daily_totals.mean()  # Spatial average of daily totals
```

**Query interpretation examples:**
- "What is the total precipitation in Florida" → Use `.sum(dim='time').sum()` (total volume)
- "What is the precipitation in Florida" → Use `.sum(dim='time').sum()` (total volume)
- "What is the accumulated precipitation in Florida" → Use `.sum(dim='time').sum()` (total volume)
- "What is the average precipitation in Florida" → Use `.sum(dim='time').mean()` (spatial average)
- "What is the daily precipitation in Florida" → Use `.sum(dim='time').mean()` (spatial average)

**Never use `.mean()` alone for precipitation - it gives hourly rates, not daily totals.**

**For other variables (temperature, humidity):**
```python
data = ds['Variable'].sel(lat=slice(...), lon=slice(...))
result = data.mean()  # This is fine for non-precipitation variables
```

**STEP 1: Check if I have complete information**
Required: Location + Time Period + Variable
- Missing any? → Ask user to specify
- Have all? → Call execute_custom_code

**STEP 2: Generate proper code based on precipitation terminology**
- "total/precipitation/accumulated": `.sum(dim='time').sum()` (total volume)
- "average precipitation": `.sum(dim='time').mean()` (spatial average)
- Other variables: `.mean()`

Available data: 2023 (daily), SPI: 2003-2023 (monthly)

**Examples of asking for missing information:**
- If missing time: "Please specify a time period for [variable] data. Available: [range]"
- If missing location: "Please specify a location (state, city, or coordinates)"
- If unclear variable: "Please clarify which weather variable you're interested in"

**Only call execute_custom_code when you have ALL required information.**

SPI/Drought Monthly Variables (use load_specific_month_spi_kerchunk):
- Drought = 'SPI3' (3-month Standardized Precipitation Index)
- SPI = 'SPI3' (values: <-1.5 severe drought, >1.5 very wet)

IMPORTANT: SPI data uses different coordinate names:
- Use 'latitude' and 'longitude' for SPI data (not 'lat' and 'lon')
- Use data.longitude, data.latitude when creating maps from SPI data

FOR WIND SPEED MAPS - copy this pattern:
```python
import builtins, json, numpy as np
lat_min, lat_max = 32.5, 42.0  # California
lon_min, lon_max = -124.4, -114.1

ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 3, 12)


# ✅ CRITICAL: Load BOTH wind components
wind_e = ds['Wind_E'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).mean(dim='time')
wind_n = ds['Wind_N'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).mean(dim='time')

# Calculate wind speed magnitude
data = np.sqrt(wind_e**2 + wind_n**2)

# Create static map
fig, ax = create_cartopy_map(data.lon, data.lat, data.values,
                             'Average Wind Speed - California, March 12, 2023',
                             'Wind Speed (m/s)', 'viridis')
mappable = ax.collections[0] if ax.collections else None
if mappable:
    vmin, vmax = mappable.get_clim()
else:
    vmin, vmax = float(np.nanmin(data.values)), float(np.nanmax(data.values))
static_url = save_plot_to_blob_simple(fig, 'wind_static.png', account_key)

# Transparent overlay
fig2 = plt.figure(figsize=(10, 8), frameon=False, dpi=200)
fig2.patch.set_alpha(0)
ax2 = fig2.add_axes([0,0,1,1])
ax2.set_axis_off()
ax2.set_facecolor('none')
ax2.set_xlim(lon_min, lon_max)
ax2.set_ylim(lat_min, lat_max)
lon_grid, lat_grid = np.meshgrid(data.lon, data.lat)
masked = np.ma.masked_invalid(data.values)
ax2.pcolormesh(lon_grid, lat_grid, masked, cmap='viridis', shading='auto', alpha=0.9, vmin=vmin, vmax=vmax)
overlay_url = save_plot_to_blob_simple(fig2, 'wind_overlay.png', account_key)

# Build GeoJSON
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
                "properties": {"value": v, "variable": "wind_speed", "unit": "m/s"}
            })
geojson = {"type": "FeatureCollection", "features": geo_features}

center_lon = float((lon_min + lon_max)/2)
center_lat = float((lat_min + lat_max)/2)
bounds = {"north": float(lat_max), "south": float(lat_min), "east": float(lon_max), "west": float(lon_min)}
map_config = {"center": [center_lon, center_lat], "zoom": 6, "style": "satellite", "overlay_mode": True}

plt.close(fig); plt.close(fig2); ds.close()
result = {
    "static_url": static_url,
    "overlay_url": overlay_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config,
    "metadata": {
        "variable": "Wind_Speed",
        "date": "2023-03-12",
        "year": 2023,
        "month": 3,
        "day": 12,
        "region": "california",
        "computation_type": "raw",
        "color_scale": {"vmin": float(vmin), "vmax": float(vmax), "cmap": "viridis"}
    }
}
```

🚨 CRITICAL: SPI DATA IS MONTHLY ONLY - NO DAILY ANIMATIONS POSSIBLE

COLOR CONSISTENCY RULE:
- The TRANSPARENT overlay MUST use EXACTLY the same colormap AND data range (vmin/vmax) as the static map.
- After creating the static map, do:
    mappable = ax.collections[0] if ax.collections else None
    if mappable:
        vmin, vmax = mappable.get_clim()
    else:
        vmin, vmax = float(np.nanmin(data.values)), float(np.nanmax(data.values))
- Then use these vmin, vmax in the overlay pcolormesh: ax2.pcolormesh(..., vmin=vmin, vmax=vmax, cmap=<same_cmap>)
- Never recompute or expand the range for the overlay; no buffers.

🚨 CRITICAL: CUSTOM COLORMAP FOR SPI/DROUGHT MAPS
For ALL SPI and drought visualizations, use this EXACT custom colormap:
```python
import matplotlib.colors as mcolors
from matplotlib.colors import LinearSegmentedColormap
colors = ['#8B0000','#CD0000','#FF0000','#FF4500','#FFA500','#FFFF00','#90EE90','#00FF00','#00CED1','#0000FF','#00008B']
cmap = LinearSegmentedColormap.from_list('spi_overlay', colors, N=256)
```

🚨 CRITICAL: For flash drought queries use this example for python coding using SPI:
```python
import builtins

# Define Great Plains region coordinates
lat_min, lat_max = 35.0, 49.0
lon_min, lon_max = -104.0, -94.0

# Load SPI data for June and August 2012
ds_june, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2012, 6)
spi_june = ds_june['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(spi_june, 'squeeze'):
    spi_june = spi_june.squeeze()

ds_august, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2012, 8)
spi_august = ds_august['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(spi_august, 'squeeze'):
    spi_august = spi_august.squeeze()

# Calculate SPI difference
delta_spi = spi_august - spi_june

# Create flash drought detection mask
flash_drought_mask = (spi_june >= 0.0) & (spi_august <= -1.5)
flash_drought_percentage = (flash_drought_mask.sum().item() / flash_drought_mask.size) * 100

# Create map visualizations
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np

fig, ax = plt.subplots(1, 1, figsize=(12, 8), subplot_kw={'projection': ccrs.PlateCarree()})
lon_grid, lat_grid = np.meshgrid(spi_august.longitude, spi_august.latitude)

# Plot SPI difference
delta_vmin, delta_vmax = -2.5, 2.5
cmap = "RdBu"
img = ax.pcolormesh(lon_grid, lat_grid, delta_spi.values, cmap=cmap, vmin=delta_vmin, vmax=delta_vmax, shading="auto", transform=ccrs.PlateCarree())

# Overlay flash drought areas with hatching
ax.contourf(lon_grid, lat_grid, flash_drought_mask.astype(float), levels=[0.5, 1.5], colors='none', hatches=['///'], transform=ccrs.PlateCarree())

# Enhance map aesthetics
ax.add_feature(cfeature.COASTLINE)
ax.add_feature(cfeature.STATES)
ax.set_title(f"Flash Drought Detection in Great Plains (June-August 2012)\\n{flash_drought_percentage:.1f}% of area affected")
plt.colorbar(img, ax=ax, orientation='vertical', label='SPI Change (Aug - Jun)')

# Save map
filename = "flash_drought_great_plains_jun_aug_2012.png"
url = save_plot_to_blob_simple(fig, filename, account_key)
plt.close(fig)
ds_june.close()
ds_august.close()

result = {
    "static_url": url,
    "overlay_url": url,  # Same for now
    "geojson": {"type": "FeatureCollection", "features": []},
    "bounds": {"north": lat_max, "south": lat_min, "east": lon_max, "west": lon_min},
    "map_config": {"center": [(lon_min+lon_max)/2, (lat_min+lat_max)/2], "zoom": 6, "style": "satellite", "overlay_mode": True}
}
```

🚨 CRITICAL: For drought recovery queries use this example for python coding using SPI:
```python
import builtins

# Define Southeast region coordinates
lat_min, lat_max = 24.0, 36.0
lon_min, lon_max = -90.0, -75.0

# Load SPI data for December 2012 and December 2013
ds_dec_2012, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2012, 12)
spi_dec_2012 = ds_dec_2012['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(spi_dec_2012, 'squeeze'):
    spi_dec_2012 = spi_dec_2012.squeeze()

ds_dec_2013, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2013, 12)
spi_dec_2013 = ds_dec_2013['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(spi_dec_2013, 'squeeze'):
    spi_dec_2013 = spi_dec_2013.squeeze()

# Calculate SPI difference
delta_spi = spi_dec_2013 - spi_dec_2012

# Create drought recovery detection mask
drought_recovery_mask = (spi_dec_2012 <= -1.0) & (spi_dec_2013 >= -1.0)
drought_recovery_percentage = (drought_recovery_mask.sum().item() / drought_recovery_mask.size) * 100

# Create map visualizations
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np

fig, ax = plt.subplots(1, 1, figsize=(12, 8), subplot_kw={'projection': ccrs.PlateCarree()})
lon_grid, lat_grid = np.meshgrid(spi_dec_2013.longitude, spi_dec_2013.latitude)

# Plot SPI difference
delta_vmin, delta_vmax = -2.5, 2.5
cmap = "RdBu"
img = ax.pcolormesh(lon_grid, lat_grid, delta_spi.values, cmap=cmap, vmin=delta_vmin, vmax=delta_vmax, shading="auto", transform=ccrs.PlateCarree())

# Overlay drought recovery areas with hatching
ax.contourf(lon_grid, lat_grid, drought_recovery_mask.astype(float), levels=[0.5, 1.5], colors='none', hatches=['///'], transform=ccrs.PlateCarree())

# Enhance map aesthetics
ax.add_feature(cfeature.COASTLINE)
ax.add_feature(cfeature.STATES)
ax.set_title(f"Drought Recovery Assessment in Southeast US (Dec 2012 - Dec 2013)\\n{drought_recovery_percentage:.1f}% of area recovered from drought")
plt.colorbar(img, ax=ax, orientation='vertical', label='SPI Change (2013 - 2012)')

# Save map
filename = "drought_recovery_southeast_dec2012_dec2013.png"
url = save_plot_to_blob_simple(fig, filename, account_key)
plt.close(fig)
ds_dec_2012.close()
ds_dec_2013.close()

result = {
    "static_url": url,
    "overlay_url": url,  # Same for now
    "geojson": {"type": "FeatureCollection", "features": []},
    "bounds": {"north": lat_max, "south": lat_min, "east": lon_max, "west": lon_min},
    "map_config": {"center": [(lon_min+lon_max)/2, (lat_min+lat_max)/2], "zoom": 6, "style": "satellite", "overlay_mode": True}
}
```

🚨 CRITICAL: When user asks about "annual trends" or "trends", calculate the annual average and do not use a fixed month, use this python code:
```python
# Annual mean SPI (default)
monthly_means = []
for m in range(1, 13):
    try:
        ds_month, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, m)
        month_spi = ds_month['SPI3'].sel(
            latitude=slice(lat_min, lat_max),
            longitude=slice(lon_min, lon_max)
        )
        if hasattr(month_spi, 'squeeze'):
            month_spi = month_spi.squeeze()
        monthly_means.append(float(month_spi.mean()))
        ds_month.close()
    except:
        continue

spi_mean = np.nanmean(monthly_means) if monthly_means else None
```

FOR DROUGHT/SPI QUERIES - copy this pattern:
```python
import builtins
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

# Trend detection FIRST
trend_keywords = ['trend', 'trends', 'over time', 'change', 'changing',
                  'drying', 'wetting', 'getting', 'multi-year']
is_trend_query = any(word in user_request.lower() for word in trend_keywords)

# Month detection ONLY IF NOT a trend
month = None
if not is_trend_query:
    month_match = re.search(
        r'(january|february|march|april|may|june|july|august|september|october|november|december)',
        user_request.lower()
    )
    if month_match:
        month_names = ['january','february','march','april','may','june',
                       'july','august','september','october','november','december']
        month = month_names.index(month_match.group(1)) + 1

# Year detection
year_match = re.search(r'(20\d{2})', user_request)
year = int(year_match.group(1)) if year_match else 2020

# FINAL behavior selection
if is_trend_query:
    # ALWAYS run annual trend code
    month = None  # Force annual-only
    # Use trend analysis pattern
else:
    if month is None:
        # User wants a single-year annual map - calculate annual average
        month = None
    else:
        # Single month map
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
    # CRITICAL: Create custom SPI colormap
    import matplotlib.colors as mcolors
    from matplotlib.colors import LinearSegmentedColormap
    colors = ['#8B0000','#CD0000','#FF0000','#FF4500','#FFA500','#FFFF00','#90EE90','#00FF00','#00CED1','#0000FF','#00008B']
    spi_cmap = LinearSegmentedColormap.from_list('spi_custom', colors, N=256)
    
    title = f"Standardized Precipitation Index (SPI) — {month_names[month-1].title()} {year}, {region_name}"
    fig, ax = create_spi_map_with_categories(data.longitude, data.latitude, data.values, title, region_name=region_name.lower())
    url = save_plot_to_blob_simple(fig, f'{region_name.lower()}_spi_{year}_{month:02d}.png', account_key)
    plt.close(fig)
    ds.close()
    result = {
    "static_url": url,
    "overlay_url": url,  # Same for now
    "geojson": {"type": "FeatureCollection", "features": []},
    "bounds": {"north": lat_max, "south": lat_min, "east": lon_max, "west": lon_min},
    "map_config": {"center": [(lon_min+lon_max)/2, (lat_min+lat_max)/2], "zoom": 6, "style": "satellite", "overlay_mode": True}
}
```

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
    result = {
    "static_url": url,
    "overlay_url": url,  # Same for now
    "geojson": {"type": "FeatureCollection", "features": []},
    "bounds": {"north": lat_max, "south": lat_min, "east": lon_max, "west": lon_min},
    "map_config": {"center": [(lon_min+lon_max)/2, (lat_min+lat_max)/2], "zoom": 6, "style": "satellite", "overlay_mode": True}
}
    
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
    result = {
    "static_url": url,
    "overlay_url": url,
    "geojson": {"type": "FeatureCollection", "features": []},
    "bounds": {"north": lat_max, "south": lat_min, "east": lon_max, "west": lon_min},
    "map_config": {"center": [(lon_min+lon_max)/2, (lat_min+lat_max)/2], "zoom": 6, "style": "satellite", "overlay_mode": True}
}
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

# CRITICAL: Create custom SPI colormap first
import matplotlib.colors as mcolors
from matplotlib.colors import LinearSegmentedColormap
colors = ['#8B0000','#CD0000','#FF0000','#FF4500','#FFA500','#FFFF00','#90EE90','#00FF00','#00CED1','#0000FF','#00008B']
spi_cmap = LinearSegmentedColormap.from_list('spi_custom', colors, N=256)

# Both use same SPI scale (-2.5 to 2.5) with CUSTOM colormap
im1 = ax1.pcolormesh(may_data.longitude, may_data.latitude, may_data.values, cmap=spi_cmap, vmin=-2.5, vmax=2.5, shading='auto', transform=ccrs.PlateCarree())
ax1.add_feature(cfeature.COASTLINE)
ax1.add_feature(cfeature.STATES)
ax1.set_title('Florida SPI - May 2023')

im2 = ax2.pcolormesh(june_data.longitude, june_data.latitude, june_data.values, cmap=spi_cmap, vmin=-2.5, vmax=2.5, shading='auto', transform=ccrs.PlateCarree())
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
result = {
    "static_url": url,
    "overlay_url": url,  # Same for now
    "geojson": {"type": "FeatureCollection", "features": []},
    "bounds": {"north": lat_max, "south": lat_min, "east": lon_max, "west": lon_min},
    "map_config": {"center": [(lon_min+lon_max)/2, (lat_min+lat_max)/2], "zoom": 6, "style": "satellite", "overlay_mode": True}
}
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
result = {
    "static_url": url,
    "overlay_url": url,  # Same for now
    "geojson": {"type": "FeatureCollection", "features": []},
    "bounds": {"north": lat_max, "south": lat_min, "east": lon_max, "west": lon_min},
    "map_config": {"center": [(lon_min+lon_max)/2, (lat_min+lat_max)/2], "zoom": 6, "style": "satellite", "overlay_mode": True}
}
```

FOR SINGLE PRECIPITATION MAPS - copy this pattern:
```python
import builtins
# Use coordinates for requested region
lat_min, lat_max = 24.5, 31.0  # Example: Florida
lon_min, lon_max = -87.6, -80.0
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 21)
data = ds['Rainf'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).sum(dim='time')
fig, ax = create_cartopy_map(data.lon, data.lat, data.values, 'Precipitation', 'Precipitation (mm)', 'Blues')
mappable = ax.collections[0] if ax.collections else None
if mappable:
    vmin, vmax = mappable.get_clim()
else:
    vmin, vmax = float(np.nanmin(data.values)), float(np.nanmax(data.values))
static_url = save_plot_to_blob_simple(fig, 'precip_static.png', account_key)
# Transparent overlay
fig2 = plt.figure(figsize=(10,8), frameon=False, dpi=200)
fig2.patch.set_alpha(0)
ax2 = fig2.add_axes([0,0,1,1]); ax2.set_axis_off(); ax2.set_facecolor('none')
ax2.set_xlim(lon_min, lon_max); ax2.set_ylim(lat_min, lat_max)
lon_grid, lat_grid = np.meshgrid(data.lon, data.lat)
masked = np.ma.masked_invalid(data.values)
ax2.pcolormesh(lon_grid, lat_grid, masked, cmap='Blues', shading='auto', alpha=0.9, vmin=vmin, vmax=vmax)
overlay_url = save_plot_to_blob_simple(fig2, 'precip_overlay.png', account_key)
# Build lightweight GeoJSON sample (every 4th point)
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
plt.close(fig); plt.close(fig2); ds.close()
result = {
    "static_url": static_url,
    "overlay_url": overlay_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config,
    "metadata": {
        "variable": "Rainf",
        "date": "2023-01-21",
        "year": 2023,
        "month": 1,
        "day": 21,
        "region": "florida",
        "computation_type": "raw",
        "color_scale": {"vmin": float(vmin), "vmax": float(vmax), "cmap": "Blues"}
    }
}
```

FOR SINGLE TEMPERATURE MAPS - copy this pattern (NOW WITH static_url + overlay_url):
```python
import builtins, json, numpy as np
lat_min, lat_max = 24.5, 31.0
lon_min, lon_max = -87.6, -80.0
ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 15)
data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max)).mean(dim='time') - 273.15

# STATIC FIG (with title/colorbar)
fig, ax = create_cartopy_map(data.lon, data.lat, data.values,
                             'Temperature', 'Temperature (°C)', 'RdYlBu_r')
mappable = ax.collections[0] if ax.collections else None
if mappable:
    vmin, vmax = mappable.get_clim()
else:
    vmin, vmax = float(np.nanmin(data.values)), float(np.nanmax(data.values))
static_url = save_plot_to_blob_simple(fig, 'temp_static.png', account_key)

# TRANSPARENT OVERLAY FIG (no axes / no colorbar) for Azure Maps
import matplotlib.pyplot as plt
fig2 = plt.figure(figsize=(10, 8), frameon=False, dpi=200)
fig2.patch.set_alpha(0)
ax2 = fig2.add_axes([0,0,1,1])
ax2.set_axis_off()
ax2.set_facecolor('none')
ax2.set_xlim(lon_min, lon_max)
ax2.set_ylim(lat_min, lat_max)
from matplotlib import cm
lon_grid, lat_grid = np.meshgrid(data.lon, data.lat)
masked = np.ma.masked_invalid(data.values)
ax2.pcolormesh(lon_grid, lat_grid, masked, cmap='RdYlBu_r', shading='auto', alpha=0.9, vmin=vmin, vmax=vmax)
overlay_url = save_plot_to_blob_simple(fig2, 'temp_overlay.png', account_key)

# GEOJSON SAMPLE
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

plt.close(fig); plt.close(fig2); ds.close()
result = {
    "static_url": static_url,
    "overlay_url": overlay_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config,
    "metadata": {
        "variable": "Tair",
        "date": "2023-01-15",
        "year": 2023,
        "month": 1,
        "day": 15,
        "region": "florida",
        "computation_type": "raw",
        "color_scale": {"vmin": float(vmin), "vmax": float(vmax), "cmap": "RdYlBu_r"}
    }
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
    result = {
    "static_url": url,
    "overlay_url": url,  # Same for now
    "geojson": {"type": "FeatureCollection", "features": []},
    "bounds": {"north": lat_max, "south": lat_min, "east": lon_max, "west": lon_min},
    "map_config": {"center": [(lon_min+lon_max)/2, (lat_min+lat_max)/2], "zoom": 6, "style": "satellite", "overlay_mode": True}
}
    
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

FOR SPI MAPS (DUAL OUTPUT):
```python
import builtins, json, numpy as np
lat_min, lat_max = 32.0, 42.0
lon_min, lon_max = -125.0, -114.0
ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, 2020, 5)
data = ds['SPI3'].sel(latitude=builtins.slice(lat_min, lat_max), longitude=builtins.slice(lon_min, lon_max))
if hasattr(data, 'squeeze'): data = data.squeeze()
fig, ax = create_spi_map_with_categories(data.longitude, data.latitude, data.values,
                                         'California SPI - May 2020', region_name='california')
# SPI map helper likely fixed scale (-2.5,2.5); capture anyway
mappable = ax.collections[0] if ax.collections else None
if mappable:
    vmin, vmax = mappable.get_clim()
else:
    vmin, vmax = -2.5, 2.5
static_url = save_plot_to_blob_simple(fig, 'spi_static.png', account_key)

# Transparent overlay (no axes)
fig2 = plt.figure(figsize=(10,8), frameon=False, dpi=200)
fig2.patch.set_alpha(0)
ax2 = fig2.add_axes([0,0,1,1]); ax2.set_axis_off(); ax2.set_facecolor('none')
ax2.set_xlim(lon_min, lon_max); ax2.set_ylim(lat_min, lat_max)
lon_grid, lat_grid = np.meshgrid(data.longitude, data.latitude)
masked = np.ma.masked_invalid(data.values)
import matplotlib.colors as mcolors
from matplotlib.colors import LinearSegmentedColormap
colors = ['#8B0000','#CD0000','#FF0000','#FF4500','#FFA500','#FFFF00','#90EE90','#00FF00','#00CED1','#0000FF','#00008B']
cmap = LinearSegmentedColormap.from_list('spi_overlay', colors, N=256)
ax2.pcolormesh(lon_grid, lat_grid, masked, cmap=cmap, vmin=vmin, vmax=vmax, shading='auto', alpha=0.9)
overlay_url = save_plot_to_blob_simple(fig2, 'spi_overlay.png', account_key)

# GEOJSON SAMPLE
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
plt.close(fig); plt.close(fig2); ds.close()
result = {
    "static_url": static_url,
    "overlay_url": overlay_url,
    "geojson": geojson,
    "bounds": bounds,
    "map_config": map_config,
    "metadata": {
        "variable": "SPI3",
        "date": "2020-05",
        "year": 2020,
        "month": 5,
        "day": None,  # SPI is monthly
        "region": "california",
        "computation_type": "raw",
        "color_scale": {"vmin": float(vmin), "vmax": float(vmax), "cmap": "spi_overlay"}
    }
}
```

RULE UPDATE (REPLACE PRIOR RULE):
FOR ANY MAP RESULT you MUST return a dict with:
- static_url (annotated figure with legend/colorbar)
- overlay_url (transparent, no axes, georeferenced)
- geojson
- bounds (north,south,east,west)
- map_config {center, zoom, style, overlay_mode}
Never return only a single URL.
"""

# ---------- Create text agent ----------
text_agent = proj.agents.create_agent(
    model=TEXT_MODEL,
    name="nldas3-merged-agent-memory-flash-drought-trends",
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
            "capabilities": [
                "memory-aware-operation",
                "flash-drought-detection",
                "drought-recovery-analysis",
                "trend-analysis",
                "speed-optimized",
                "advanced-precipitation-handling",
                "direct-code-execution",
                "subplot-creation",
                "proper-colorbar-scaling",
                "map-generation",
                "formatted-time-series"
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

print(f"✅ Created MERGED text agent: {text_agent.id}")
print(f"✅ Created visualization agent: {viz_agent.id}")
print("\n🎉 MERGED agent features:")
print("  ✅ Memory-aware operation (from File 1)")
print("  ✅ Flash drought detection (from File 2)")
print("  ✅ Drought recovery analysis (from File 2)")
print("  ✅ Trend analysis capabilities (from File 2)")
print("  ✅ Speed optimization (from File 2)")
print("  ✅ Advanced precipitation handling (from File 2)")
print("  ✅ Proper colorbar scaling")
print("  ✅ Shared color scales for comparisons")
print("  ✅ Formatted time series with proper axes")
print("  ✅ Custom SPI colormap")
print("\n📄 Saved agent_info.json")