import json
import xarray as xr
import fsspec
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import os
import re
import traceback
import builtins
import logging
from datetime import datetime, timedelta

# Configure matplotlib BEFORE any other imports
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import io
import base64

# --- Kerchunk container configuration ---
KERCHUNK_CONTAINER = "kerchunk"
KERCHUNK_COMBINED_BLOB = f"{KERCHUNK_CONTAINER}/kerchunk_combined.json"
KERCHUNK_INDIV_PREFIX = "kerchunk_"

# Azure configuration
TENANT_ID = "4ba2629f-3085-4f9a-b2ec-3962de0e3490"
CLIENT_ID = "768b7315-6661-498c-b826-c2689a5d790e"
CLIENT_SECRET = "l._8Q~bLceP-UjSOiTyil2~dAe92MPW6htpBFblU"
VAULT_URL = "https://ainldas34754142228.vault.azure.net/"
VAULT_SECRET = "blob-storage"
ACCOUNT_NAME = "ainldas34950184597"

# Variable mapping from common terms to NLDAS variable names
VARIABLE_MAPPING = {
    "temperature": "Tair",
    "temp": "Tair",
    "air_temperature": "Tair",
    "precipitation": "Rainf",
    "precip": "Rainf", 
    "rainfall": "Rainf",
    "rain": "Rainf",
    "humidity": "Qair",
    "specific_humidity": "Qair",
    "moisture": "Qair",
    "wind": "Wind_E",
    "wind_speed": "Wind_E",
    "wind_east": "Wind_E",
    "wind_north": "Wind_N",
    "pressure": "PSurf",
    "surface_pressure": "PSurf",
    "longwave": "LWdown",
    "longwave_radiation": "LWdown", 
    "lw_radiation": "LWdown",
    "shortwave": "SWdown",
    "shortwave_radiation": "SWdown",
    "sw_radiation": "SWdown",
    "solar": "SWdown",
    "solar_radiation": "SWdown",
    "radiation": "LWdown"
}

def get_mapped_variable(variable: str, available_vars: list):
    """
    Map a variable name to NLDAS variable name and validate it exists.
    Returns (mapped_variable, suggestions)
    """
    if variable in available_vars:
        return variable, []
    
    mapped = VARIABLE_MAPPING.get(variable.lower())
    if mapped and mapped in available_vars:
        return mapped, []
    
    suggestions = []
    for common_name, nldas_name in VARIABLE_MAPPING.items():
        if nldas_name in available_vars:
            suggestions.append(f"For {common_name} use '{nldas_name}'")
    
    return None, suggestions

def get_account_key():
    """Get storage account key from Azure Key Vault."""
    cred = ClientSecretCredential(tenant_id=TENANT_ID, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    return SecretClient(vault_url=VAULT_URL, credential=cred).get_secret(VAULT_SECRET).value

def _kerchunk_fs(account_name: str, account_key: str):
    """Filesystem for listing/reading kerchunk JSON blobs."""
    return fsspec.filesystem("abfs", account_name=account_name, account_key=account_key)

def _discover_kerchunk_index(account_name: str, account_key: str, prefer_combined: bool = True):
    """
    Discover and load kerchunk reference JSON from the kerchunk container.
    Returns (refs_dict, blob_path_used, is_combined)
    """
    fs = _kerchunk_fs(account_name, account_key)

    if prefer_combined and fs.exists(KERCHUNK_COMBINED_BLOB):
        with fs.open(KERCHUNK_COMBINED_BLOB, "r") as f:
            return json.load(f), KERCHUNK_COMBINED_BLOB, True

    try:
        entries = fs.ls(KERCHUNK_CONTAINER)
    except FileNotFoundError:
        raise FileNotFoundError(f"Kerchunk container '{KERCHUNK_CONTAINER}' not found")

    json_blobs = sorted(
        e for e in entries
        if e.endswith(".json") and e.split("/")[-1].startswith(KERCHUNK_INDIV_PREFIX)
    )
    if not json_blobs:
        raise FileNotFoundError(f"No kerchunk JSON files found in '{KERCHUNK_CONTAINER}'")

    first_blob = json_blobs[0]
    with fs.open(first_blob, "r") as f:
        return json.load(f), first_blob, False

def load_nldas_from_kerchunk(account_name: str, account_key: str, prefer_combined: bool = True):
    """
    Open an xarray Dataset via kerchunk refs stored in the kerchunk container.
    Returns (dataset, debug_info)
    """
    refs, blob_used, is_combined = _discover_kerchunk_index(account_name, account_key, prefer_combined=prefer_combined)

    debug = {
        "kerchunk_container": KERCHUNK_CONTAINER,
        "kerchunk_blob_used": blob_used,
        "kerchunk_is_combined": is_combined,
        "kerchunk_ref_count": len(refs.get("refs", {})),
    }

    mapper = fsspec.get_mapper(
        "reference://",
        fo=refs,
        remote_protocol="az",
        remote_options={"account_name": account_name, "account_key": account_key},
    )

    ds = xr.open_dataset(mapper, engine="zarr", backend_kwargs={"consolidated": False})
    return ds, debug

def parse_date_to_nldas_format(year: int, month: int, day: int):
    """
    Convert year, month, day to NLDAS date format and datetime object
    """
    dt = datetime(year, month, day)
    # NLDAS format: A20230103 for 2023-01-03
    nldas_date = f"A{year:04d}{month:02d}{day:02d}"
    return nldas_date, dt

def find_available_kerchunk_files(account_name: str, account_key: str):
    """
    Find all available kerchunk files in the container
    """
    fs = _kerchunk_fs(account_name, account_key)
    
    try:
        entries = fs.ls(KERCHUNK_CONTAINER)
    except FileNotFoundError:
        return []
    
    json_blobs = [
        e for e in entries
        if e.endswith(".json") and KERCHUNK_INDIV_PREFIX in e.split("/")[-1]
    ]
    
    available_dates = []
    for blob_path in json_blobs:
        filename = blob_path.split("/")[-1]
        
        # Extract date from filename like "kerchunk_NLDAS_FOR0010_H.A20230103.030.beta.json"
        date_match = re.search(r'\.A(\d{8})\.', filename)
        if date_match:
            date_str = date_match.group(1)
            try:
                year = int(date_str[:4])
                month = int(date_str[4:6])
                day = int(date_str[6:8])
                dt = datetime(year, month, day)
                
                available_dates.append({
                    "date": dt,
                    "filename": filename,
                    "nldas_format": f"A{date_str}",
                    "path": blob_path
                })
            except ValueError:
                continue
    
    # Sort by date
    available_dates.sort(key=lambda x: x["date"])
    return available_dates

def load_specific_date_kerchunk(account_name: str, account_key: str, year: int, month: int, day: int):
    """
    Load kerchunk data for a specific date with enhanced error handling
    """
    # Format the date as NLDAS expects
    nldas_date, dt = parse_date_to_nldas_format(year, month, day)
    
    # Build expected filename
    expected_filename = f"kerchunk_NLDAS_FOR0010_H.{nldas_date}.030.beta.json"
    expected_path = f"{KERCHUNK_CONTAINER}/{expected_filename}"
    
    try:
        fs = _kerchunk_fs(account_name, account_key)
        
        if fs.exists(expected_path):
            try:
                # Check file size first
                file_info = fs.info(expected_path)
                file_size = file_info.get('size', 0)
                logging.info(f"Loading kerchunk file: {expected_path} (size: {file_size} bytes)")
                
                if file_size == 0:
                    raise ValueError(f"Kerchunk file {expected_path} is empty (0 bytes)")
                
                # Load the specific date file
                with fs.open(expected_path, "r") as f:
                    content = f.read()
                    
                if not content.strip():
                    raise ValueError(f"Kerchunk file {expected_path} contains no data")
                
                # Try to parse JSON
                try:
                    refs = json.loads(content)
                except json.JSONDecodeError as je:
                    # Show first 200 chars of content for debugging
                    content_preview = content[:200] if len(content) > 200 else content
                    raise ValueError(f"Invalid JSON in {expected_path}. Error: {je}. Content preview: {content_preview}")
                
            except Exception as file_error:
                logging.error(f"Error loading {expected_path}: {file_error}")
                # Fall back to finding available dates
                available_dates = find_available_kerchunk_files(account_name, account_key)
                
                if not available_dates:
                    raise FileNotFoundError("No valid kerchunk files found")
                
                # Use the first available date as fallback
                fallback = available_dates[0]
                logging.info(f"Using fallback date: {fallback['date'].date()}")
                
                fallback_path = f"{KERCHUNK_CONTAINER}/{fallback['filename']}"
                
                try:
                    with fs.open(fallback_path, "r") as f:
                        refs = json.load(f)
                except Exception as fallback_error:
                    raise Exception(f"Both primary and fallback files failed. Primary error: {file_error}. Fallback error: {fallback_error}")
                
                debug = {
                    "kerchunk_container": KERCHUNK_CONTAINER,
                    "kerchunk_blob_used": fallback_path,
                    "kerchunk_is_combined": False,
                    "requested_date": str(dt.date()),
                    "actual_date": str(fallback["date"].date()),
                    "fallback_reason": str(file_error),
                    "nldas_date_format": fallback["nldas_format"],
                    "kerchunk_ref_count": len(refs.get("refs", {})),
                }
            else:
                # File loaded successfully
                debug = {
                    "kerchunk_container": KERCHUNK_CONTAINER,
                    "kerchunk_blob_used": expected_path,
                    "kerchunk_is_combined": False,
                    "requested_date": str(dt.date()),
                    "nldas_date_format": nldas_date,
                    "kerchunk_ref_count": len(refs.get("refs", {})),
                    "file_size_bytes": file_size,
                }
            
            mapper = fsspec.get_mapper(
                "reference://",
                fo=refs,
                remote_protocol="az",
                remote_options={"account_name": account_name, "account_key": account_key},
            )
            
            ds = xr.open_dataset(mapper, engine="zarr", backend_kwargs={"consolidated": False})
            return ds, debug
            
        else:
            # File doesn't exist, find closest date
            available_dates = find_available_kerchunk_files(account_name, account_key)
            
            if not available_dates:
                raise FileNotFoundError("No kerchunk files found")
            
            # Show available dates for debugging
            date_list = [d['date'].strftime('%Y-%m-%d') for d in available_dates[:5]]
            logging.info(f"Requested date {dt.date()} not found. Available dates: {date_list}")
            
            # Find closest date
            target_date = dt
            closest = min(available_dates, key=lambda x: abs((x["date"] - target_date).days))
            days_diff = abs((closest["date"] - target_date).days)
            
            if days_diff > 7:  # Don't use data more than 7 days away
                available_range = f"{available_dates[0]['date'].date()} to {available_dates[-1]['date'].date()}"
                raise FileNotFoundError(
                    f"Date {dt.date()} not available. Closest date is {closest['date'].date()} ({days_diff} days away). "
                    f"Available dates: {available_range}"
                )
            
            # Load closest date
            closest_path = f"{KERCHUNK_CONTAINER}/{closest['filename']}"
            logging.info(f"Loading closest date: {closest_path}")
            
            try:
                with fs.open(closest_path, "r") as f:
                    refs = json.load(f)
            except json.JSONDecodeError as je:
                raise Exception(f"Invalid JSON in closest date file {closest_path}: {je}")
            
            debug = {
                "kerchunk_container": KERCHUNK_CONTAINER,
                "kerchunk_blob_used": closest_path,
                "kerchunk_is_combined": False,
                "requested_date": str(dt.date()),
                "actual_date": str(closest["date"].date()),
                "days_difference": days_diff,
                "nldas_date_format": closest["nldas_format"],
                "kerchunk_ref_count": len(refs.get("refs", {})),
            }
            
            mapper = fsspec.get_mapper(
                "reference://",
                fo=refs,
                remote_protocol="az",
                remote_options={"account_name": account_name, "account_key": account_key},
            )
            
            ds = xr.open_dataset(mapper, engine="zarr", backend_kwargs={"consolidated": False})
            return ds, debug
            
    except Exception as e:
        raise Exception(f"Failed to load kerchunk data for {dt.date()}: {str(e)}")

def save_plot_to_blob_simple(figure, filename, account_key):
    """
    Save matplotlib figure to Azure Blob Storage and return the URL.
    """
    try:
        # Save figure to bytes
        buffer = io.BytesIO()
        figure.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
        buffer.seek(0)
        
        # Upload to blob storage
        blob_service_client = BlobServiceClient(
            account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
            credential=account_key
        )
        
        container_name = "visualizations"
        
        # Create container if it doesn't exist (private is fine)
        try:
            container_client = blob_service_client.get_container_client(container_name)
            if not container_client.exists():
                blob_service_client.create_container(container_name)
                logging.info(f"Created container: {container_name}")
        except Exception as container_error:
            logging.warning(f"Container warning: {container_error}")
        
        blob_client = blob_service_client.get_blob_client(
            container=container_name, 
            blob=filename
        )
        
        # Upload the image
        blob_client.upload_blob(buffer.getvalue(), overwrite=True)
        
        # Generate a SAS URL for access (valid for 24 hours)
        sas_token = generate_blob_sas(
            account_name=ACCOUNT_NAME,
            container_name=container_name,
            blob_name=filename,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=24)
        )
        
        # Return the blob URL with SAS token
        blob_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{container_name}/{filename}?{sas_token}"
        logging.info(f"Image saved to: {blob_url}")
        return blob_url
        
    except Exception as e:
        raise Exception(f"Failed to save to blob storage: {str(e)}")

def create_weather_map_with_blob_storage(ds, variable, region_name, lat_min, lat_max, lon_min, lon_max, year, month, day=None):
    """
    Create weather map and save to blob storage - returns URL
    """
    fig = None
    try:
        # Set matplotlib backend
        plt.switch_backend('Agg')
        
        # Extract data
        data = ds[variable].isel(time=0).sel(
            lat=builtins.slice(lat_min, lat_max),   
            lon=builtins.slice(lon_min, lon_max)    
        )
        
        logging.info(f"Data shape: {data.shape}")
        
        # Create plot
        fig, ax = plt.subplots(figsize=(12, 8))
        im = data.plot(ax=ax, cmap="viridis")
        
        # Get variable info
        units = data.attrs.get('units', 'unknown')
        long_name = data.attrs.get('long_name', variable)
        
        # Format date and filename
        date_str = f"{year}-{month:02d}"
        if day:
            date_str += f"-{day:02d}"
        
        plt.title(f'{region_name} {long_name}\n{date_str}', fontsize=14, fontweight='bold')
        plt.xlabel('Longitude')
        plt.ylabel('Latitude')
        
        # Create filename
        filename = f"{region_name}_{variable}_{year}_{month:02d}"
        if day:
            filename += f"_{day:02d}"
        filename += "_map.png"
        
        # Save to blob storage
        account_key = get_account_key()
        blob_url = save_plot_to_blob_simple(fig, filename, account_key)
        plt.close(fig)
        
        return {
            "status": "created",
            "format": "png",
            "blob_url": blob_url,
            "filename": filename,
            "description": f"Weather map for {long_name} - {date_str}",
            "note": "Image saved to blob storage and accessible via URL"
        }
        
    except Exception as e:
        if fig:
            plt.close(fig)
        raise Exception(f"Map creation failed: {str(e)}")

def handle_weather_function_call(args: dict):
    """
    Handles weather function calls with blob storage support
    """
    # Set matplotlib backend
    import matplotlib
    matplotlib.use('Agg')
    
    debug_info = {
        "approach": "blob_storage_response",
        "visualization_requested": args.get("create_visualization", False)
    }

    try:
        # Step 1: Get account key
        account_key = get_account_key()

        # Step 2: Load dataset
        ds, kdbg = load_nldas_from_kerchunk(ACCOUNT_NAME, account_key, prefer_combined=True)
        # Only keep essential debug info
        debug_info["kerchunk_loaded"] = True
        debug_info["kerchunk_is_combined"] = kdbg.get("kerchunk_is_combined", False)

        # Step 3: Map variable
        variable = args.get("variable", "LWdown")
        available_vars = list(ds.data_vars)
        mapped_variable, suggestions = get_mapped_variable(variable, available_vars)
        
        if not mapped_variable:
            ds.close()
            return {
                "status": "error",
                "error": f"Variable '{variable}' not found",
                "suggestions": suggestions[:3],  # Limit suggestions
                "debug": debug_info
            }
        
        # Step 4: Get coordinates
        lat_min = args.get("lat_min", 37.9)
        lat_max = args.get("lat_max", 39.7) 
        lon_min = args.get("lon_min", -79.5)
        lon_max = args.get("lon_max", -75.0)
        
        # Step 5: Extract data
        region_data = ds[mapped_variable].isel(time=0).sel(
            lat=builtins.slice(lat_min, lat_max),
            lon=builtins.slice(lon_min, lon_max)
        )

        # Quick stats
        average_val = float(region_data.mean().values)
        min_val = float(region_data.min().values)
        max_val = float(region_data.max().values)
        units = region_data.attrs.get('units', 'unknown')
        long_name = region_data.attrs.get('long_name', mapped_variable)

        # Build COMPACT result
        result = {
            "status": "success",
            "variable": {
                "name": mapped_variable,
                "units": units,
                "description": long_name
            },
            "region_stats": {
                "average": f"{average_val:.2f}",
                "range": f"{min_val:.2f} to {max_val:.2f}",
                "units": units,
                "grid_points": int(region_data.size)
            },
            "coordinates": {
                "lat_range": f"{lat_min} to {lat_max}",
                "lon_range": f"{lon_min} to {lon_max}"
            }
        }

        # Step 6: Handle visualization request - ALWAYS CREATE MAP FOR "map" REQUESTS
        create_map = args.get("create_visualization", False)
        
        # Auto-detect map requests from query
        if not create_map:
            query_text = str(args).lower()
            map_keywords = ["map", "plot", "chart", "visualization", "visualize", "show", "display"]
            create_map = any(keyword in query_text for keyword in map_keywords)
            debug_info["auto_detected_map_request"] = create_map
        
        if create_map:
            try:
                viz_result = create_weather_map_with_blob_storage(
                    ds, mapped_variable, "Region",
                    lat_min, lat_max, lon_min, lon_max,
                    args.get("year", 2023),
                    args.get("month", 1),
                    args.get("day")
                )
                result["visualization"] = viz_result
                result["note"] = "Data retrieved and map created with blob URL"
                debug_info["blob_url_created"] = True
            except Exception as e:
                result["visualization_error"] = f"Map creation failed: {str(e)}"
                result["note"] = "Data retrieved but map creation failed"
                debug_info["blob_url_created"] = False
        else:
            result["note"] = "Data retrieved successfully - no visualization requested"
            debug_info["blob_url_created"] = False
        
        # Close dataset
        ds.close()
        
        # Add minimal debug info
        result["debug"] = debug_info
        
        return result

    except Exception as e:
        return {
            "status": "error",
            "error": f"Processing failed: {str(e)}",
            "debug": debug_info
        }

# Add these functions at the end of your working weather_tool.py file:

import time

# Azure Maps configuration
AZURE_MAPS_KEY = "YOUR_AZURE_MAPS_SUBSCRIPTION_KEY"  # Replace with your actual key

def save_geojson_to_blob(data, filename, account_key):
    """Convert xarray data to GeoJSON and save to blob storage"""
    try:
        logging.info(f"Converting data to GeoJSON format for {filename}")
        
        # Convert xarray to GeoJSON format
        features = []
        
        # Get coordinates and values
        if hasattr(data, 'lat') and hasattr(data, 'lon'):
            lats = data.lat.values
            lons = data.lon.values
            
            # Handle time dimension
            if 'time' in data.dims:
                values = data.isel(time=0).values
            else:
                values = data.values
            
            # Create grid of points
            for i, lat in enumerate(lats):
                for j, lon in enumerate(lons):
                    if not np.isnan(values[i, j]):
                        feature = {
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [float(lon), float(lat)]
                            },
                            "properties": {
                                "value": float(values[i, j]),
                                "variable": getattr(data, 'name', 'data') or 'data'
                            }
                        }
                        features.append(feature)
            
            geojson = {
                "type": "FeatureCollection",
                "features": features
            }
        else:
            raise ValueError("Data must have 'lat' and 'lon' coordinates")
        
        # Save to blob storage (reuse existing blob service client setup)
        blob_service_client = BlobServiceClient(
            account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
            credential=account_key
        )
        
        container_name = "visualizations"
        blob_name = f"interactive/{filename}"
        
        blob_client = blob_service_client.get_blob_client(
            container=container_name, 
            blob=blob_name
        )
        
        geojson_str = json.dumps(geojson, indent=2)
        blob_client.upload_blob(geojson_str, overwrite=True, content_type='application/json')
        
        # Generate SAS URL
        sas_token = generate_blob_sas(
            account_name=ACCOUNT_NAME,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=7)
        )
        
        geojson_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
        
        logging.info(f"GeoJSON saved with {len(geojson['features'])} features: {geojson_url}")
        return geojson_url
        
    except Exception as e:
        logging.error(f"Error saving GeoJSON to blob: {e}")
        raise

def create_azure_map_html(data_url, variable_type, center_coords):
    """Generate HTML with Azure Maps showing weather data"""
    try:
        logging.info(f"Creating Azure Maps HTML for {variable_type}")
        
        # Color schemes for different variables
        color_schemes = {
            'temperature': ['#0000FF', '#00FFFF', '#FFFF00', '#FF0000'],  # Blue to Red
            'precipitation': ['#FFFFFF', '#ADD8E6', '#0000FF', '#000080'], # White to Navy
            'humidity': ['#FFFFFF', '#90EE90', '#008000', '#006400']      # White to Green
        }
        
        colors = color_schemes.get(variable_type.lower(), ['#FFFFFF', '#FF0000'])
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>NLDAS-3 {variable_type.title()} - Interactive Map</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    
    <!-- Azure Maps Web SDK -->
    <link rel="stylesheet" href="https://atlas.microsoft.com/sdk/javascript/mapcontrol/2/atlas.min.css" />
    <script src="https://atlas.microsoft.com/sdk/javascript/mapcontrol/2/atlas.min.js"></script>
    
    <style>
        body {{ margin: 0; padding: 0; font-family: Arial, sans-serif; }}
        #map {{ position: relative; width: 100%; height: 100vh; }}
        .legend {{ 
            position: absolute; top: 10px; right: 10px; 
            background: rgba(255,255,255,0.9); padding: 15px; 
            border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.3); 
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="legend">
        <h3>NLDAS-3 {variable_type.title()}</h3>
        <p>Click points for exact values</p>
    </div>
    
    <script>
        var map = new atlas.Map('map', {{
            center: {center_coords},
            zoom: 8,
            style: 'satellite_road_labels',
            authOptions: {{
                authType: 'subscriptionKey',
                subscriptionKey: '{AZURE_MAPS_KEY}'
            }}
        }});
        
        map.events.add('ready', function() {{
            fetch('{data_url}')
                .then(response => response.json())
                .then(data => {{
                    var datasource = new atlas.source.DataSource();
                    map.sources.add(datasource);
                    datasource.add(data);
                    
                    var values = data.features.map(f => f.properties.value);
                    var minVal = Math.min(...values);
                    var maxVal = Math.max(...values);
                    
                    var heatMapLayer = new atlas.layer.HeatMapLayer(datasource, null, {{
                        radius: 20,
                        color: [
                            'interpolate', ['linear'], ['get', 'value'],
                            minVal, '{colors[0]}',
                            maxVal, '{colors[-1]}'
                        ],
                        intensity: 0.7
                    }});
                    
                    map.layers.add(heatMapLayer);
                    
                    var popup = new atlas.Popup();
                    map.events.add('click', heatMapLayer, function(e) {{
                        if (e.shapes && e.shapes.length > 0) {{
                            var properties = e.shapes[0].getProperties();
                            popup.setOptions({{
                                content: '<div style="padding:10px"><strong>{variable_type.title()}: ' + properties.value.toFixed(3) + '</strong></div>',
                                position: e.shapes[0].getCoordinates()
                            }});
                            popup.open(map);
                        }}
                    }});
                }});
        }});
    </script>
</body>
</html>
        """
        
        # Save HTML to blob storage
        timestamp = int(time.time())
        filename = f"map_{variable_type}_{timestamp}.html"
        
        blob_service_client = BlobServiceClient(
            account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
            credential=account_key
        )
        
        container_name = "visualizations"
        blob_name = f"interactive/{filename}"
        
        blob_client = blob_service_client.get_blob_client(
            container=container_name,
            blob=blob_name
        )
        
        blob_client.upload_blob(html_content, overwrite=True, content_type='text/html')
        
        # Generate SAS URL
        sas_token = generate_blob_sas(
            account_name=ACCOUNT_NAME,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(days=7)
        )
        
        html_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
        
        logging.info(f"Azure Maps HTML created: {html_url}")
        return html_url
        
    except Exception as e:
        logging.error(f"Error creating Azure Maps HTML: {e}")
        raise