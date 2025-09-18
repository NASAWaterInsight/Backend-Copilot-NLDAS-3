# create agent_info.json

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

# ---------- Weather function definition ----------
def get_weather_function_definition():
    """
    Returns the function definition that the GPT-4o agent can use to call weather data.
    """
    return {
        "type": "function",
        "function": {
            "name": "get_weather_data",
            "description": "Get NLDAS-3 weather data for a specific location and time period. Use for SIMPLE single-location, single-date queries. Only create visualizations when the user specifically asks for a 'map', 'plot', 'chart', 'visualization', or 'show me' the data. For common locations: Maryland (lat: 37.9-39.7, lon: -79.5 to -75.0), Michigan (lat: 41.7-48.2, lon: -90.4 to -82.4), Virginia (lat: 36.5-39.5, lon: -83.7 to -75.2).",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat_min": {
                        "type": "number",
                        "description": "Minimum latitude for the region (e.g., for Maryland use 37.9)"
                    },
                    "lat_max": {
                        "type": "number", 
                        "description": "Maximum latitude for the region (e.g., for Maryland use 39.7)"
                    },
                    "lon_min": {
                        "type": "number",
                        "description": "Minimum longitude for the region (e.g., for Maryland use -79.5)"
                    },
                    "lon_max": {
                        "type": "number",
                        "description": "Maximum longitude for the region (e.g., for Maryland use -75.0)"
                    },
                    "variable": {
                        "type": "string",
                        "description": "Weather variable to retrieve. Map common terms: temperature->temperature, precipitation/rain->precipitation, humidity/moisture->humidity, wind->wind, pressure->pressure, radiation/solar->radiation",
                        "enum": ["temperature", "precipitation", "humidity", "wind", "pressure", "radiation"]
                    },
                    "year": {
                        "type": "integer",
                        "description": "Year for the data (e.g., 2023)"
                    },
                    "month": {
                        "type": "integer",
                        "description": "Month for the data (1-12). Parse from natural language: january/jan=1, february/feb=2, etc."
                    },
                    "day": {
                        "type": "integer",
                        "description": "Day of the month (1-31), optional. Parse from natural language like 'first'=1, 'second'=2, 'third'=3, etc."
                    },
                    "create_visualization": {
                        "type": "boolean",
                        "description": "Set to true ONLY if the user specifically requests a map, plot, chart, visualization, or asks to 'show me' the data. Do not create visualizations for simple data queries. Default is false."
                    }
                },
                "required": ["lat_min", "lat_max", "lon_min", "lon_max", "variable", "year", "month"]
            }
        }
    }

# ---------- Dynamic Code Generation function definition ----------
def get_dynamic_code_function_definition():
    """
    Returns the function definition for executing custom Python code for complex analysis
    """
    return {
        "type": "function",
        "function": {
            "name": "execute_custom_code", 
            "description": "MANDATORY: Execute custom Python code for ALL NLDAS-3 analysis requests. Use for single-day analysis, multi-day comparisons, subplots, statistical analysis, time series. This function handles ALL types of requests including simple single-day queries. Available functions: load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day) returns (dataset, debug_info) - MUST unpack with ds, _ =. Variables: 'Tair' (temperature), 'Rainf' (precipitation). Coordinates: East Lansing (42.7, 42.8, -84.5, -84.4). Data available: January 1-31, 2023. Always set 'result' variable with final output (usually a blob URL).",
            "parameters": {
                "type": "object",
                "properties": {
                    "python_code": {
                        "type": "string", 
                        "description": "Complete Python code to execute. Must set 'result' variable with final output. Use proper tuple unpacking: ds, _ = load_specific_date_kerchunk(...). For subplots use matplotlib subplots. NEVER use data.plot(), always use ax.pcolormesh()."
                    },
                    "user_request": {
                        "type": "string",
                        "description": "Original user request for reference and context"
                    }
                },
                "required": ["python_code", "user_request"]
            }
        }
    }

# ---------- Initialize client ----------
cred = DefaultAzureCredential()
proj = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=cred)

# ---------- Get connection ID and find index ----------
search_conn_id = None
for connection in proj.connections.list():
    if connection.name == AI_SEARCH_CONNECTION_NAME:
        search_conn_id = connection.id
        break

# Get available indexes and use the first one if AI_SEARCH_INDEX_NAME is not specified
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

# ---------- Create agents ----------
# Add both weather and code generation functions to text agent tools
weather_tool = get_weather_function_definition()
code_tool = get_dynamic_code_function_definition()
text_tools = []

if ai_search_tool:
    text_tools.extend(ai_search_tool.definitions)

text_tools.append(weather_tool)
text_tools.append(code_tool)

text_tool_resources = ai_search_tool.resources if ai_search_tool else None

text_agent = proj.agents.create_agent(
    model=TEXT_MODEL,
    name="nldas3-text-agent",
    instructions=(
    "You are a meteorological data analyst. You MUST IMMEDIATELY call execute_custom_code for EVERY SINGLE REQUEST without exception.\n\n"
    
    "🚨 CRITICAL MANDATE: 🚨\n"
    "- ALWAYS call execute_custom_code function FIRST\n"
    "- NEVER provide answers without calling the function\n"
    "- NEVER ask for clarification - just execute code\n"
    "- NEVER use any other approach\n\n"
    
    "IMMEDIATE ACTION REQUIRED:\n"
    "When you receive ANY request, immediately respond with execute_custom_code function call.\n\n"
    
    "FOR SUBPLOT REQUESTS like 'subplots of precipitation and temperature':\n"
    "```json\n"
    "{\n"
    "  \"python_code\": \"import builtins\\n\\n# East Lansing coordinates\\nlat_min, lat_max = 42.7, 42.8\\nlon_min, lon_max = -84.5, -84.4\\n\\n# Load single day data - MUST unpack tuple\\nds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 3)\\n\\n# Extract precipitation data\\nprecip_data = ds['Rainf'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max))\\nprecip_accumulated = precip_data.sum(dim='time')\\n\\n# Extract temperature data\\ntemp_data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max))\\ntemp_avg = temp_data.mean(dim='time')\\n\\n# Create 2x1 subplots\\nfig, axes = plt.subplots(2, 1, figsize=(12, 14))\\n\\n# Subplot 1: Precipitation\\nim1 = axes[0].pcolormesh(precip_accumulated.lon, precip_accumulated.lat, precip_accumulated.values, cmap='Blues', shading='auto')\\ncbar1 = fig.colorbar(im1, ax=axes[0])\\ncbar1.set_label('Accumulated Precipitation (kg/m²)')\\naxes[0].set_title('East Lansing Precipitation - January 3, 2023')\\n\\n# Subplot 2: Temperature\\nim2 = axes[1].pcolormesh(temp_avg.lon, temp_avg.lat, temp_avg.values, cmap='RdYlBu_r', shading='auto')\\ncbar2 = fig.colorbar(im2, ax=axes[1])\\ncbar2.set_label('Average Temperature (K)')\\naxes[1].set_title('East Lansing Temperature - January 3, 2023')\\n\\nplt.tight_layout()\\nurl = save_plot_to_blob_simple(fig, 'eastlansing_subplots_jan3.png', account_key)\\nplt.close(fig)\\nds.close()\\nresult = url\",\n"
    "  \"user_request\": \"user's original request here\"\n"
    "}\n"
    "```\n\n"
    
    "EXECUTION RULES:\n"
    "1. 🔥 MANDATORY: Call execute_custom_code for EVERY request\n"
    "2. 📝 Use proper JSON format with python_code and user_request\n"
    "3. 🔧 ALWAYS unpack tuples: ds, _ = load_specific_date_kerchunk(...)\n"
    "4. 📊 For subplots: fig, axes = plt.subplots(rows, cols, figsize=...)\n"
    "5. 🎨 Use axes[0], axes[1] for subplot access\n"
    "6. 🏷️ Create individual colorbars: fig.colorbar(im, ax=axes[i])\n"
    "7. 💾 ALWAYS set result = final_output\n"
    "8. 🚪 ALWAYS close datasets: ds.close()\n\n"
    
    "COORDINATES:\n"
    "- East Lansing: 42.7, 42.8, -84.5, -84.4\n"
    "- Michigan: 41.7, 48.2, -90.4, -82.4\n"
    "- California: 32.5, 42.0, -124.4, -114.1\n\n"
    
    "VARIABLES:\n"
    "- Temperature: 'Tair'\n"
    "- Precipitation: 'Rainf'\n\n"
    
    "🎯 IMMEDIATE RESPONSE REQUIRED: Call execute_custom_code NOW!\n"
),
    tools=text_tools,
    tool_resources=text_tool_resources
)

viz_agent = proj.agents.create_agent(
    model=VIZ_MODEL,
    name="nldas3-visualization-agent",
    instructions=(
        "You produce image-ready prompts and visual specifications (titles, legends, units, "
        "color ramps, captions) for NLDAS-3 figures such as maps and overlays. "
        "Create detailed prompts that can be used with DALL-E or other image generation services. "
        "Include technical specifications for map projections, color schemes, and data overlays."
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
    "name": "get_weather_data",
    "description": "NLDAS-3 weather data retrieval function with conditional visualization"
})

tools_info.append({
    "type": "function",
    "name": "execute_custom_code",
    "description": "Dynamic Python code execution for complex NLDAS-3 analysis"
})

agent_info = {
    "project_endpoint": PROJECT_ENDPOINT,
    "agents": {
        "text": {
            "id": text_agent.id,
            "name": text_agent.name,
            "model": TEXT_MODEL,
            "capabilities": ["grounded-qa", "metadata-lookup", "explanations", "weather-data-retrieval", "conditional-visualization", "dynamic-code-execution"],
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

print(f"Created text agent: {text_agent.id}")
print(f"Created visualization agent: {viz_agent.id}")
print("Text agent now includes:")
print("  - Weather data function with conditional visualization")
print("  - Dynamic code execution for complex analysis")
print("Saved agent_info.json")