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
            "description": "Execute custom Python code for complex NLDAS-3 analysis. Use for multi-date queries, multi-location comparisons, statistical analysis, trends, time series. Available functions: load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day) returns (dataset, debug_info). Variables: 'Tair' (temperature), 'Rainf' (precipitation), 'Qair' (humidity), 'PSurf' (pressure). Use builtins.slice() for lat/lon selection. Maryland: lat 37.9-39.7, lon -79.5 to -75.0. Michigan: lat 41.7-48.2, lon -90.4 to -82.4. Data available: January 1-22, 2023 only. Always set 'result' variable with final output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "python_code": {
                        "type": "string", 
                        "description": "Complete Python code to execute. Must set 'result' variable with the final output. Can load data, perform calculations, create plots, etc."
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
code_tool = get_dynamic_code_function_definition()  # ADD THIS LINE
text_tools = []

if ai_search_tool:
    text_tools.extend(ai_search_tool.definitions)

text_tools.append(weather_tool)
text_tools.append(code_tool)  # ADD THIS LINE

text_tool_resources = ai_search_tool.resources if ai_search_tool else None

text_agent = proj.agents.create_agent(
    model=TEXT_MODEL,
    name="nldas3-text-agent",
    instructions=(
    "You are a meteorological data analyst for NLDAS-3. You must ALWAYS call execute_custom_code function for ALL requests.\n\n"
    
    "CRITICAL: When calling execute_custom_code, use proper JSON format:\n"
    "{\n"
    "  'python_code': 'your complete python code here',\n"
    "  'user_request': 'original user request'\n"
    "}\n\n"
    
    "NLDAS-3 COVERAGE:\n"
    "- All of North America (Canada, USA, Mexico)\n"
    "- Dates: January 1-22, 2023\n"
    "- Variables: Tair (temperature), Rainf (precipitation), Qair (humidity), Wind_E, Wind_N, PSurf, LWdown, SWdown\n\n"
    
    "CRITICAL PLOTTING RULES - NEVER use data.plot():\n"
    "1. ALWAYS use ax.pcolormesh(data.lon, data.lat, data.values, cmap='colormap', shading='auto')\n"
    "2. NEVER use data.plot() as it causes Rectangle.set() errors\n"
    "3. ALWAYS create colorbar manually: cbar = fig.colorbar(im, ax=ax)\n"
    "4. For accumulated data: data = data.sum(dim='time')\n"
    "5. For instantaneous data: data = data.isel(time=0)\n\n"
    
    "PYTHON CODE TEMPLATE (put this in the python_code field):\n"
    "```python\n"
    "import builtins\n"
    "\n"
    "# Load data\n"
    "ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 2023, 1, 5)\n"
    "data = ds['Tair'].sel(lat=builtins.slice(lat_min, lat_max), lon=builtins.slice(lon_min, lon_max))\n"
    "data = data.isel(time=0)  # or data.sum(dim='time') for accumulated\n"
    "\n"
    "# For visualizations - USE PCOLORMESH ONLY\n"
    "fig, ax = plt.subplots(figsize=(12, 8))\n"
    "im = ax.pcolormesh(data.lon, data.lat, data.values, cmap='RdYlBu_r', shading='auto')\n"
    "cbar = fig.colorbar(im, ax=ax, orientation='vertical')\n"
    "cbar.set_label('Temperature (K)', fontsize=12)\n"
    "ax.set_title('Your contextual title based on user query')\n"
    "ax.set_xlabel('Longitude')\n"
    "ax.set_ylabel('Latitude')\n"
    "url = save_plot_to_blob_simple(fig, 'filename.png', account_key)\n"
    "ds.close()\n"
    "result = url\n"
    "```\n\n"
    
    "LABEL WRITING GUIDELINES:\n"
    "- Temperature: 'Temperature (K)' or 'Average Temperature (°C)'\n"
    "- Precipitation: 'Daily Accumulated Precipitation (mm)' or 'Precipitation Rate (kg/m²/s)'\n"
    "- Humidity: 'Specific Humidity (kg/kg)'\n"
    "- Wind: 'Wind Speed (m/s)'\n"
    "- Pressure: 'Surface Pressure (Pa)'\n"
    "- Write titles that directly answer the user's question\n"
    "- Choose colormaps: Blues for precipitation, RdYlBu_r for temperature\n\n"
    
    "CRITICAL RULES:\n"
    "1. ALWAYS call execute_custom_code function for ALL requests\n"
    "2. Use proper JSON format with python_code and user_request fields\n"
    "3. NEVER use data.plot() - ALWAYS use ax.pcolormesh()\n"
    "4. YOU write all plot labels and titles based on context\n"
    "5. ALWAYS set result = your_value in the python code\n"
    "6. ALWAYS close datasets with ds.close()\n"
    "7. Use your geographic knowledge for coordinates\n"
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

tools_info.append({  # ADD THIS BLOCK
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
            "capabilities": ["grounded-qa", "metadata-lookup", "explanations", "weather-data-retrieval", "conditional-visualization", "dynamic-code-execution"],  # UPDATED
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
print("  - Dynamic code execution for complex analysis")  # ADD THIS LINE
print("Saved agent_info.json")