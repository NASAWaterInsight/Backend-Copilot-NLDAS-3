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
        # First, get list of available dates to handle padding errors gracefully
        available_dates = find_available_kerchunk_files(account_name, account_key)
        
        if not available_dates:
            raise FileNotFoundError("No kerchunk files found in container")
        
        # Check if requested date is available
        requested_date_available = any(
            d["date"].date() == dt.date() for d in available_dates
        )
        
        if not requested_date_available:
            # Find closest available date
            logging.warning(f"Date {dt.date()} not available. Finding closest date...")
            target_date = dt
            closest = min(available_dates, key=lambda x: abs((x["date"] - target_date).days))
            days_diff = abs((closest["date"] - target_date).days)
            
            if days_diff > 7:  # Don't use data more than 7 days away
                available_range = f"{available_dates[0]['date'].date()} to {available_dates[-1]['date'].date()}"
                raise FileNotFoundError(
                    f"Date {dt.date()} not available. Closest date is {closest['date'].date()} ({days_diff} days away). "
                    f"Available dates: {available_range}"
                )
            
            # Use closest date
            expected_path = closest["path"]
            expected_filename = closest["filename"]
            logging.info(f"Using closest available date: {closest['date'].date()}")
        
        fs = _kerchunk_fs(account_name, account_key)
        
        try:
            # Check file size first
            file_info = fs.info(expected_path)
            file_size = file_info.get('size', 0)
            logging.info(f"Loading kerchunk file: {expected_path} (size: {file_size} bytes)")
            
            if file_size == 0:
                raise ValueError(f"Kerchunk file {expected_path} is empty (0 bytes)")
            
            # Load the file with enhanced error handling
            with fs.open(expected_path, "r") as f:
                content = f.read()
                
            if not content.strip():
                raise ValueError(f"Kerchunk file {expected_path} contains no data")
            
            # Try to parse JSON with better error handling
            try:
                if not content or not content.strip():
                    raise ValueError(f"Kerchunk file {expected_path} is empty or contains only whitespace")
                
                # Log content preview for debugging
                content_preview = content[:100] if content else "EMPTY"
                logging.debug(f"JSON content preview: {content_preview}")
                
                refs = json.loads(content)
                
            except json.JSONDecodeError as je:
                # Enhanced error logging
                logging.error(f"JSON decode error in {expected_path}: {je}")
                logging.error(f"Content length: {len(content) if content else 0}")
                logging.error(f"Content preview: {content[:200] if content else 'EMPTY'}")
                
                # If JSON parsing fails, try fallback immediately
                raise ValueError(f"Invalid JSON in {expected_path}. Error: {je}")
            
            # Validate refs structure
            if not isinstance(refs, dict) or "refs" not in refs:
                raise ValueError(f"Invalid kerchunk structure in {expected_path}")
            
        except Exception as file_error:
            logging.error(f"Error loading {expected_path}: {file_error}")
            
            # Enhanced fallback logic - try multiple available dates
            fallback_attempts = 0
            max_fallback_attempts = 3
            
            for fallback_candidate in available_dates[:max_fallback_attempts]:
                if fallback_candidate["path"] == expected_path:
                    continue  # Skip the one that failed
                
                fallback_attempts += 1
                logging.info(f"Trying fallback {fallback_attempts}: {fallback_candidate['date'].date()}")
                
                try:
                    fallback_path = fallback_candidate["path"]
                    with fs.open(fallback_path, "r") as f:
                        fallback_content = f.read()
                    
                    if not fallback_content.strip():
                        continue
                    
                    refs = json.loads(fallback_content)
                    
                    if isinstance(refs, dict) and "refs" in refs:
                        logging.info(f"Successfully loaded fallback date: {fallback_candidate['date'].date()}")
                        
                        debug = {
                            "kerchunk_container": KERCHUNK_CONTAINER,
                            "kerchunk_blob_used": fallback_path,
                            "kerchunk_is_combined": False,
                            "requested_date": str(dt.date()),
                            "actual_date": str(fallback_candidate["date"].date()),
                            "fallback_reason": f"Original file error: {str(file_error)}",
                            "nldas_date_format": fallback_candidate["nldas_format"],
                            "kerchunk_ref_count": len(refs.get("refs", {})),
                            "fallback_attempt": fallback_attempts
                        }
                        break
                        
                except Exception as fallback_error:
                    logging.warning(f"Fallback {fallback_attempts} failed: {fallback_error}")
                    continue
            else:
                # All fallbacks failed
                raise Exception(f"All fallback attempts failed. Original error: {file_error}")
        else:
            # Original file loaded successfully
            debug = {
                "kerchunk_container": KERCHUNK_CONTAINER,
                "kerchunk_blob_used": expected_path,
                "kerchunk_is_combined": False,
                "requested_date": str(dt.date()),
                "nldas_date_format": nldas_date,
                "kerchunk_ref_count": len(refs.get("refs", {})),
                "file_size_bytes": file_size,
            }
        
        # Create mapper and open dataset
        try:
            mapper = fsspec.get_mapper(
                "reference://",
                fo=refs,
                remote_protocol="az",
                remote_options={"account_name": account_name, "account_key": account_key},
            )
            
            ds = xr.open_dataset(mapper, engine="zarr", backend_kwargs={"consolidated": False})
            return ds, debug
            
        except Exception as mapper_error:
            logging.error(f"Error creating mapper or opening dataset: {mapper_error}")
            raise Exception(f"Failed to open dataset: {str(mapper_error)}")
            
    except Exception as e:
        # Enhanced error message with available dates
        available_dates_list = [d['date'].strftime('%Y-%m-%d') for d in available_dates[:5]] if available_dates else ["None"]
        error_msg = f"Failed to load kerchunk data for {dt.date()}: {str(e)}. Available dates: {available_dates_list}"
        logging.error(error_msg)
        raise Exception(error_msg)

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

# Add a mapping for descriptive variable labels
VARIABLE_LABELS = {
    "Tair": "Temperature (K)",
    "Rainf": "Accumulated Precipitation (mm)",
    "Qair": "Specific Humidity (kg/kg)",
    "PSurf": "Surface Pressure (Pa)",
    "LWdown": "Longwave Radiation (W/m²)",
    "SWdown": "Shortwave Radiation (W/m²)"
}

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
        im = data.plot(ax=ax, cmap="viridis", add_colorbar=False)
        
        # Get descriptive label for the variable
        variable_label = VARIABLE_LABELS.get(variable, variable)  # Fallback to raw name if not found
        
        # Add color bar with descriptive label
        cbar = fig.colorbar(im, ax=ax, orientation="vertical")
        cbar.set_label(variable_label, fontsize=12)
        
        # Format date and filename
        date_str = f"{year}-{month:02d}"
        if day:
            date_str += f"-{day:02d}"
        
        plt.title(f'{region_name} {variable_label}\n{date_str}', fontsize=14, fontweight='bold')
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
            "description": f"Weather map for {variable_label} - {date_str}",
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
        result["debug"] = debug_info
        
        return result

    except Exception as e:
        return {
            "status": "error",
            "error": f"Processing failed: {str(e)}",
            "debug": debug_info
        }
        
        return result

    except Exception as e:
        return {
            "status": "error",
            "error": f"Processing failed: {str(e)}",
            "debug": debug_info
        }