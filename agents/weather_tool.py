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
# Add these cache variables after the existing imports
_KERCHUNK_FILES_CACHE = None
_CACHE_TIMESTAMP = None
_CACHE_DURATION = 300  # 5 minutes in seconds

# --- Kerchunk container configuration ---
KERCHUNK_CONTAINER = "kerchunk"
KERCHUNK_COMBINED_BLOB = f"{KERCHUNK_CONTAINER}/kerchunk_combined.json"
KERCHUNK_INDIV_PREFIX = "kerchunk_"
# NEW: SPI Drought container configuration
SPI_KERCHUNK_CONTAINER = "spi-kerchunk-rechunked"
SPI_KERCHUNK_PREFIX = "kerchunk_SPI3_"

# NEW: Drought-related keywords
DROUGHT_KEYWORDS = [
    "drought", "spi", "standardized precipitation index", "dry", "wet", 
    "aridity", "dryness", "moisture deficit", "precipitation anomaly"
]

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
    "radiation": "LWdown",
    "spi": "SPI3",
    "spi3": "SPI3", 
    "standardized_precipitation_index": "SPI3",
    "drought_index": "SPI3",
    "drought": "SPI3",
    "precipitation_anomaly": "SPI3"
}
def _get_cached_available_files(account_name: str, account_key: str):
    """
    Get cached list of available kerchunk files to avoid repeated API calls
    """
    global _KERCHUNK_FILES_CACHE, _CACHE_TIMESTAMP
    
    import time
    current_time = time.time()
    
    # Check if cache is valid
    if (_KERCHUNK_FILES_CACHE is not None and 
        _CACHE_TIMESTAMP is not None and 
        (current_time - _CACHE_TIMESTAMP) < _CACHE_DURATION):
        logging.info("📋 Using cached file list")
        return _KERCHUNK_FILES_CACHE
    
    # Cache miss - fetch and cache
    logging.info("🔄 Refreshing file list cache")
    available_dates = find_available_kerchunk_files(account_name, account_key)
    
    # Update cache
    _KERCHUNK_FILES_CACHE = available_dates
    _CACHE_TIMESTAMP = current_time
    
    # Log availability info only on cache refresh
    if available_dates:
        first_date = available_dates[0]['date']
        last_date = available_dates[-1]['date']
        total_days = len(available_dates)
        logging.info(f"📅 Data available: {first_date.strftime('%Y-%m-%d')} to {last_date.strftime('%Y-%m-%d')} ({total_days} days)")
        
        years_available = sorted(set(d['date'].year for d in available_dates))
        months_available = sorted(set(d['date'].month for d in available_dates))
        logging.info(f"📊 Years available: {years_available}")
        logging.info(f"📊 Months available: {months_available}")
    
    return available_dates
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
    
    # ENHANCED: Add note about full year availability
    suggestions.append("📅 Full year 2023 data available (January-December)")
    
    return None, suggestions

def get_account_key():
    """Get storage account key from Azure Key Vault with enhanced validation."""
    try:
        cred = ClientSecretCredential(tenant_id=TENANT_ID, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        secret_client = SecretClient(vault_url=VAULT_URL, credential=cred)
        secret = secret_client.get_secret(VAULT_SECRET)
        
        # ENHANCED: Clean and validate the key
        raw_key = secret.value
        if not raw_key:
            raise ValueError("Empty key retrieved from Key Vault")
        
        # Clean the key - remove whitespace and newlines
        cleaned_key = raw_key.strip().replace('\n', '').replace('\r', '').replace(' ', '')
        
        # Validate Base64 format by attempting to decode
        try:
            import base64
            base64.b64decode(cleaned_key)
            logging.info(f"✅ Storage key validated - length: {len(cleaned_key)} chars")
        except Exception as decode_error:
            logging.error(f"❌ Invalid Base64 key from Key Vault: {decode_error}")
            logging.error(f"❌ Key preview: {cleaned_key[:20]}...{cleaned_key[-10:] if len(cleaned_key) > 30 else ''}")
            raise ValueError(f"Invalid Base64 storage key: {decode_error}")
        
        return cleaned_key
        
    except Exception as e:
        logging.error(f"Failed to get account key: {e}")
        # EMERGENCY FALLBACK: Try with a fresh client credential
        try:
            logging.info("🔄 Trying fresh credential for Key Vault...")
            fresh_cred = ClientSecretCredential(
                tenant_id=TENANT_ID, 
                client_id=CLIENT_ID, 
                client_secret=CLIENT_SECRET
            )
            fresh_client = SecretClient(vault_url=VAULT_URL, credential=fresh_cred)
            fresh_secret = fresh_client.get_secret(VAULT_SECRET)
            fresh_key = fresh_secret.value.strip().replace('\n', '').replace('\r', '').replace(' ', '')
            
            # Validate again
            import base64
            base64.b64decode(fresh_key)
            logging.info("✅ Fresh key retrieved and validated")
            return fresh_key
            
        except Exception as fresh_error:
            logging.error(f"❌ Fresh credential also failed: {fresh_error}")
            raise Exception(f"Could not retrieve valid storage key after retry: {fresh_error}")

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



def _discover_kerchunk_index_for_date(account_name: str, account_key: str, blob_path: str):
    """
    Load a specific kerchunk file by path
    Returns (refs_dict, blob_path_used, is_combined)
    """
    fs = _kerchunk_fs(account_name, account_key)
    
    try:
        with fs.open(blob_path, "r") as f:
            refs = json.load(f)
        return refs, blob_path, False
    except Exception as e:
        raise Exception(f"Failed to load kerchunk file {blob_path}: {str(e)}")

def save_plot_to_blob_simple(fig, filename: str, account_key: str):
    """
    Save a matplotlib figure to Azure Blob Storage and return the URL
    RESTORED: Original working version from your code
    """
    try:
        # Save figure to memory buffer
        buffer = io.BytesIO()
        fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
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
        
        # Upload the image - ORIGINAL WORKING METHOD
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
        logging.error(f"Failed to save plot to blob storage: {e}")
        raise Exception(f"Failed to save plot to blob storage: {str(e)}")
def load_specific_date_kerchunk(account_name: str, account_key: str, year: int, month: int, day: int):
    """
    FAST VERSION - Direct file access like manual code
    Minimal validation, direct file reading
    """
    # Basic validation only
    if month < 1 or month > 12:
        raise ValueError(f"Month must be 1-12. Requested: {month}")
    if day < 1 or day > 31:
        raise ValueError(f"Day must be 1-31. Requested: {day}")
    
    # Direct path construction (like your manual code)
    nldas_date = f"A{year:04d}{month:02d}{day:02d}"
    expected_filename = f"kerchunk_NLDAS_FOR0010_H.{nldas_date}.030.beta.json"
    expected_path = f"{KERCHUNK_CONTAINER}/{expected_filename}"
    
    # ADD THIS LINE - Simple progress logging
    logging.info(f"📁 Loading {expected_filename}")
    
    # Direct file access (like your manual code)
    fs = _kerchunk_fs(account_name, account_key)
    
    try:
        # FAST: Direct file read (no validation overhead)
        with fs.open(expected_path, 'r') as f:
            refs = json.load(f)
        
        # Skip complex debug info - just the essentials
        debug = {"file_used": expected_filename}
        
        # Direct dataset creation
        mapper = fsspec.get_mapper(
            "reference://",
            fo=refs,
            remote_protocol="az",
            remote_options={"account_name": account_name, "account_key": account_key},
        )
        
        ds = xr.open_dataset(mapper, engine="zarr", backend_kwargs={"consolidated": False})
        return ds, debug
        
    except Exception as e:
        # Simple error - no extensive fallback logic
        raise Exception(f"Failed to load {expected_filename}: {str(e)}")

def handle_weather_function_call(function_args: dict):
    """
    Handle weather function calls from the agent
    """
    try:
        # Get account key
        account_key = get_account_key()
        
        # Extract parameters
        lat_min = function_args.get("lat_min")
        lat_max = function_args.get("lat_max") 
        lon_min = function_args.get("lon_min")
        lon_max = function_args.get("lon_max")
        variable = function_args.get("variable")
        year = function_args.get("year")
        month = function_args.get("month")
        day = function_args.get("day", 1)  # Default to 1st of month
        create_visualization = function_args.get("create_visualization", False)
        
        logging.info(f"Weather function call: {variable} for {year}-{month:02d}-{day:02d}")
        logging.info(f"Region: lat {lat_min}-{lat_max}, lon {lon_min}-{lon_max}")
        logging.info(f"Create visualization: {create_visualization}")
        
        # Load the data
        ds, debug_info = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
        
        # Map variable name
        available_vars = list(ds.data_vars.keys())
        mapped_var, suggestions = get_mapped_variable(variable, available_vars)
        
        if not mapped_var:
            return {
                "status": "error",
                "error": f"Variable '{variable}' not found. Available: {available_vars}",
                "suggestions": suggestions
            }
        
        # Extract data for the region
        try:
            data = ds[mapped_var].sel(
                lat=slice(lat_min, lat_max),
                lon=slice(lon_min, lon_max)
            )
            
            # Calculate statistics
            if mapped_var == 'Rainf':
                # Sum precipitation over time
                daily_total = data.sum(dim='time')
                value = float(daily_total.mean().values)
                unit = "mm" if mapped_var == 'Rainf' else ds[mapped_var].attrs.get('units', 'unknown')
            else:
                # Average for other variables
                daily_avg = data.mean(dim='time')
                value = float(daily_avg.mean().values)
                unit = ds[mapped_var].attrs.get('units', 'unknown')
            
            result = {
                "status": "success",
                "variable": mapped_var,
                "value": value,
                "unit": unit,
                "date": f"{year}-{month:02d}-{day:02d}",
                "region": f"lat {lat_min}-{lat_max}, lon {lon_min}-{lon_max}",
                "debug": debug_info
            }
            
            # Create visualization if requested
            if create_visualization:
                try:
                    fig, ax = plt.subplots(figsize=(10, 8))
                    
                    # Plot the daily average/sum
                    if mapped_var == 'Rainf':
                        plot_data = daily_total
                        title = f"Daily Total {mapped_var} - {year}-{month:02d}-{day:02d}"
                        cmap = 'Blues'
                    else:
                        plot_data = daily_avg
                        title = f"Daily Average {mapped_var} - {year}-{month:02d}-{day:02d}"
                        cmap = 'viridis'
                    
                    im = ax.pcolormesh(plot_data.lon, plot_data.lat, plot_data.values, 
                                     cmap=cmap, shading='auto')
                    
                    cbar = fig.colorbar(im, ax=ax)
                    cbar.set_label(f"{mapped_var} ({unit})", fontsize=16)
                    
                    ax.set_title(title, fontsize=16)
                    ax.set_xlabel('Longitude', fontsize=16)
                    ax.set_ylabel('Latitude', fontsize=16)
                    
                    # Save to blob storage
                    filename = f"{mapped_var}_{year}{month:02d}{day:02d}_{lat_min}_{lat_max}_{lon_min}_{lon_max}.png"
                    blob_url = save_plot_to_blob_simple(fig, filename, account_key)
                    
                    plt.close(fig)
                    
                    result["visualization"] = {
                        "url": blob_url,
                        "filename": filename
                    }
                    
                except Exception as viz_error:
                    logging.error(f"Visualization creation failed: {viz_error}")
                    result["visualization_error"] = str(viz_error)
            
            ds.close()
            return result
            
        except Exception as e:
            ds.close()
            raise Exception(f"Data extraction failed: {str(e)}")
            
    except Exception as e:
        logging.error(f"Weather function call failed: {e}")
        return {
            "status": "error", 
            "error": str(e)
        }

def detect_data_source(query_text: str):
    """
    Detect whether query is about drought/SPI or regular NLDAS variables
    Returns: ("spi", "monthly") or ("nldas", "daily")
    """
    query_lower = query_text.lower()
    
    # Check for drought-related keywords
    for keyword in DROUGHT_KEYWORDS:
        if keyword in query_lower:
            logging.info(f"🔍 Detected drought query (keyword: '{keyword}')")
            return "spi", "monthly"
    
    # Default to NLDAS daily data
    return "nldas", "daily"

def find_available_spi_files(account_name: str, account_key: str):
    """
    Find all available SPI kerchunk files (monthly format: kerchunk_SPI3_YYYYMM.json)
    """
    fs = _kerchunk_fs(account_name, account_key)
    
    try:
        entries = fs.ls(SPI_KERCHUNK_CONTAINER)
    except FileNotFoundError:
        return []
    
    json_blobs = [
        e for e in entries
        if e.endswith(".json") and SPI_KERCHUNK_PREFIX in e.split("/")[-1]
    ]
    
    available_dates = []
    for blob_path in json_blobs:
        filename = blob_path.split("/")[-1]
        date_match = re.search(r'SPI3_(\d{6})\.', filename)
        if date_match:
            date_str = date_match.group(1)
            try:
                year = int(date_str[:4])
                month = int(date_str[4:6])
                dt = datetime(year, month, 1)
                
                available_dates.append({
                    "date": dt,
                    "filename": filename,
                    "spi_format": date_str,
                    "path": blob_path
                })
            except ValueError:
                continue
    
    available_dates.sort(key=lambda x: x["date"])
    return available_dates

def save_computed_data_to_blob(data_array, lon_array, lat_array, metadata, account_key):
    """
    Save computed data array to blob storage for tile generation
    
    Args:
        data_array: numpy array of computed values
        lon_array: longitude coordinates
        lat_array: latitude coordinates
        metadata: dict with variable, date, computation details
        account_key: Azure storage account key
    
    Returns:
        str: blob URL and hash for the saved data
    """
    import pickle
    import hashlib
    from azure.storage.blob import BlobServiceClient
    import numpy as np
    
    # Create a unique filename based on computation
    computation_str = f"{metadata.get('variable')}_{metadata.get('date')}_{metadata.get('computation_type', 'raw')}"
    data_hash = hashlib.md5(computation_str.encode()).hexdigest()[:8]
    filename = f"computed_data_{data_hash}.pkl"
    
    # Package data - ensure numpy arrays
    data_package = {
        'data': np.asarray(data_array),
        'lon': np.asarray(lon_array),
        'lat': np.asarray(lat_array),
        'metadata': metadata
    }
    
    # Serialize to pickle
    pickled_data = pickle.dumps(data_package)
    
    # Upload to blob
    blob_service_client = BlobServiceClient(
        account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
        credential=account_key
    )
    
    container_name = "visualizations"
    blob_client = blob_service_client.get_blob_client(
        container=container_name,
        blob=filename
    )
    
    blob_client.upload_blob(pickled_data, overwrite=True)
    blob_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{container_name}/{filename}"
    
    logging.info(f"💾 Saved computed data to: {blob_url}")
    logging.info(f"   Hash: {data_hash}")
    
    return blob_url, data_hash

def load_specific_month_spi_kerchunk(account_name: str, account_key: str, year: int, month: int):
    """
    Load SPI kerchunk data for a specific month (format: YYYYMM)
    """
    # Format as YYYYMM
    spi_date = f"{year:04d}{month:02d}"
    
    # Validate inputs
    if month < 1 or month > 12:
        raise ValueError(f"Month must be 1-12. Requested: {month}")
    
    # Build expected filename
    expected_filename = f"kerchunk_SPI3_{spi_date}.json"
    expected_path = f"{SPI_KERCHUNK_CONTAINER}/{expected_filename}"
    
    try:
        # Get list of available SPI dates
        available_dates = find_available_spi_files(account_name, account_key)
        
        if available_dates:
            first_date = available_dates[0]['date']
            last_date = available_dates[-1]['date']
            total_months = len(available_dates)
            logging.info(f"📅 SPI data available: {first_date.strftime('%Y-%m')} to {last_date.strftime('%Y-%m')} ({total_months} months)")
        
        # Try to load the exact file
        fs = _kerchunk_fs(account_name, account_key)
        
        if fs.exists(expected_path):
            logging.info(f"✅ Found SPI file: {expected_filename}")
            refs, blob_used, is_combined = _discover_kerchunk_index_for_date(account_name, account_key, expected_path)
        else:
            # Find closest available month
            target_dt = datetime(year, month, 1)
            if available_dates:
                closest = min(available_dates, key=lambda x: abs((x["date"] - target_dt).days))
                days_diff = abs((closest["date"] - target_dt).days)
                
                if days_diff > 90:  # More than ~3 months away
                    available_range = f"{available_dates[0]['date'].strftime('%Y-%m')} to {available_dates[-1]['date'].strftime('%Y-%m')}"
                    raise FileNotFoundError(
                        f"SPI data for {year:04d}-{month:02d} not available. "
                        f"Closest is {closest['date'].strftime('%Y-%m')} ({days_diff} days away). "
                        f"Available range: {available_range}"
                    )
                
                # Use closest month
                expected_path = closest["path"]
                expected_filename = closest["filename"]
                logging.info(f"Using closest SPI month: {closest['date'].strftime('%Y-%m')} (requested: {year:04d}-{month:02d})")
                
                refs, blob_used, is_combined = _discover_kerchunk_index_for_date(account_name, account_key, expected_path)
            else:
                raise FileNotFoundError(f"No SPI kerchunk data found in {SPI_KERCHUNK_CONTAINER}")
        
        # Create the dataset
        debug = {
            "kerchunk_container": SPI_KERCHUNK_CONTAINER,
            "kerchunk_blob_used": blob_used,
            "data_type": "spi_monthly",
            "requested_month": f"{year:04d}-{month:02d}",
            "available_range": f"{available_dates[0]['date'].strftime('%Y-%m')} to {available_dates[-1]['date'].strftime('%Y-%m')}" if available_dates else "unknown"
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
        error_msg = f"Failed to load SPI data for {year:04d}-{month:02d}: {str(e)}"
        logging.error(error_msg)
        raise Exception(error_msg)