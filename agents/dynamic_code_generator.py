import json
import logging
import traceback
import builtins

def analyze_extreme_regions(user_request: str):
    """
    Pre-written analysis function that finds extreme regions without agent code generation.
    ❌ REMOVED: Default time values - must be explicitly provided in query
    """
    try:
        import re
        import numpy as np
        import builtins  # CRITICAL: Add this import
        from .weather_tool import (
            load_specific_date_kerchunk, 
            load_specific_month_spi_kerchunk,
            get_account_key,
            ACCOUNT_NAME
        )
        
        logging.info(f"🔍 Direct analysis function called for: {user_request}")
        
        user_query_lower = user_request.lower()
        
        # Extract number of regions (default 3)
        num_regions = 3
        num_match = re.search(r'(\d+)', user_request)
        if num_match:
            num_regions = int(num_match.group(1))
        
        # Dynamic coordinate detection using EXACT pattern from instructions
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
        else:
            lat_min, lat_max = 38.8, 39.8
            lon_min, lon_max = -79.5, -75.0
            region_name = 'Maryland'
        
        # Extract year and month - NO DEFAULTS
        year_match = re.search(r'(20\d{2})', user_request)
        if not year_match:
            return {
                "status": "error",
                "error": "No year specified in query. Please specify a year (e.g., '2023')."
            }
        year = int(year_match.group(1))
        
        month_match = re.search(r'(january|february|march|april|may|june|july|august|september|october|november|december)', user_request.lower())
        if not month_match:
            return {
                "status": "error", 
                "error": "No month specified in query. Please specify a month (e.g., 'May', 'January')."
            }
        month_names = ['january','february','march','april','may','june','july','august','september','october','november','december']
        month = month_names.index(month_match.group(1)) + 1
        
        # Get account key
        account_key = get_account_key()
        
        # FIXED: Use SPI for drought analysis, temperature for others
        if 'spi' in user_query_lower or 'drought' in user_query_lower:
            variable_type = 'SPI3'
            analysis_type = 'most significant drought regions'
            
            # Load SPI data with CORRECT syntax
            ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, month)
            data = ds[variable_type].sel(
                latitude=builtins.slice(lat_min, lat_max), 
                longitude=builtins.slice(lon_min, lon_max)
            )
            coord_names = ('latitude', 'longitude')
        else:
            variable_type = 'Tair'
            analysis_type = 'extreme temperature regions'
            
            # Load regular data
            ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, 15)
            data = ds[variable_type].sel(
                lat=builtins.slice(lat_min, lat_max),
                lon=builtins.slice(lon_min, lon_max)
            ).mean(dim='time')
            if variable_type == 'Tair':
                data = data - 273.15
            coord_names = ('lat', 'lon')
        
        # Squeeze extra dimensions
        if hasattr(data, 'squeeze'):
            data = data.squeeze()
        
        # Get coordinate arrays and data values CORRECTLY
        if variable_type == 'SPI3':
            lon_vals = data.longitude.values
            lat_vals = data.latitude.values
        else:
            lon_vals = data.lon.values
            lat_vals = data.lat.values
        
        data_vals = data.values
        
        # FIXED: Use np.meshgrid and flatten for analysis
        lon_grid, lat_grid = np.meshgrid(lon_vals, lat_vals)
        flat_data = data_vals.flatten()
        flat_lon = lon_grid.flatten()
        flat_lat = lat_grid.flatten()
        
        # Remove NaN values
        valid_mask = ~np.isnan(flat_data)
        valid_data = flat_data[valid_mask]
        valid_lon = flat_lon[valid_mask]
        valid_lat = flat_lat[valid_mask]
        
        if len(valid_data) == 0:
            ds.close()
            return {
                "status": "error",
                "error": f"No valid data found for {region_name} in {month_names[month-1]} {year}"
            }
        
        # FIXED: Find actual most extreme values using np.argsort
        if variable_type == 'SPI3' or 'drought' in user_query_lower:
            # For drought, lowest values are most significant
            extreme_indices = np.argsort(valid_data)[:num_regions]
        elif 'hottest' in user_query_lower or 'warmest' in user_query_lower:
            extreme_indices = np.argsort(valid_data)[-num_regions:][::-1]
        elif 'coldest' in user_query_lower:
            extreme_indices = np.argsort(valid_data)[:num_regions]
        else:
            # Default to most extreme drought conditions
            extreme_indices = np.argsort(valid_data)[:num_regions]
        
        # Build results with CORRECT severity classification
        regions = []
        for i, idx in enumerate(extreme_indices):
            value = float(valid_data[idx])
            lat_coord = float(valid_lat[idx])
            lon_coord = float(valid_lon[idx])
            
            # Determine severity correctly
            if variable_type == 'SPI3':
                if value <= -2.0:
                    severity = "extreme drought"
                elif value <= -1.5:
                    severity = "severe drought"
                elif value <= -1.0:
                    severity = "moderate drought"
                elif value <= -0.5:
                    severity = "mild drought"
                else:
                    severity = "near normal"
            else:
                median_temp = float(np.median(valid_data))
                if value > median_temp:
                    severity = "hottest"
                else:
                    severity = "coldest"
            
            regions.append({
                "rank": i + 1,
                "latitude": lat_coord,
                "longitude": lon_coord,
                "value": value,
                "severity": severity
            })
        
        # Create GeoJSON - FIXED format
        geo_features = []
        for region in regions:
            geo_features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [region["longitude"], region["latitude"]]
                },
                "properties": {
                    "rank": region["rank"],
                    "value": region["value"],
                    "severity": region["severity"],
                    "variable": variable_type
                }
            })
        
        geojson = {"type": "FeatureCollection", "features": geo_features}
        bounds = {
            "north": float(lat_max),
            "south": float(lat_min), 
            "east": float(lon_max),
            "west": float(lon_min)
        }
        map_config = {
            "center": [float((lon_min + lon_max)/2), float((lat_min + lat_max)/2)],
            "zoom": 7,
            "style": "satellite",
            "overlay_mode": True
        }
        
        ds.close()
        
        result = {
            "analysis_type": analysis_type,
            "variable": variable_type,
            "regions": regions,
            "geojson": geojson,
            "bounds": bounds,
            "map_config": map_config
        }
        
        logging.info(f"✅ Direct analysis completed: found {len(regions)} regions")
        return {
            "status": "success",
            "result": result
        }
        
    except Exception as e:
        logging.error(f"❌ Direct analysis failed: {e}")
        return {
            "status": "error",
            "error": f"Analysis failed: {str(e)}"
        }

def execute_custom_code(args: dict):
    """
    Execute custom Python code with proper NLDAS-3 environment setup
    """
    try:
        user_request = args.get("user_request", "Unknown request")
        python_code = args.get("python_code", "")

        # NEW: Check if this is an SPI query without time period
        if ('spi' in user_request.lower() or 'drought' in user_request.lower()) and not any(word in user_request.lower() for word in ['2020', '2021', '2022', '2023', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']):
            logging.info(f"🔍 Detected SPI query without time period - using latest available data")
            
            # Return error asking for time period
            return {
                "status": "error",
                "error": f"Please specify a time period for SPI data. Available data: 2003-01 to 2023-12. Example: 'What is the SPI in East Lansing for December 2023?'",
                "user_request": user_request,
                "available_range": "2003-01 to 2023-12",
                "suggestion": "Try: 'What is the SPI in East Lansing for December 2023?'"
            }

        # NEW: Check if this is a temperature query without time period  
        if ('temperature' in user_request.lower() or 'temp' in user_request.lower()) and not any(word in user_request.lower() for word in ['2023', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']):
            logging.info(f"🔍 Detected temperature query without time period")
            
            # Return error asking for time period
            return {
                "status": "error", 
                "error": f"Please specify a time period for temperature data. Available data: 2023 (January-December). Example: 'What is the temperature in East Lansing for May 2023?'",
                "user_request": user_request,
                "available_range": "2023 (January-December)",
                "suggestion": "Try: 'What is the temperature in East Lansing for May 2023?'"
            }

        # Continue with existing analysis query check
        analysis_keywords = ['most significant', 'most extreme', 'hottest', 'coldest', 'warmest', 'wettest', 'driest', 'highest', 'lowest', 'top', 'worst', 'best', 'find', 'where are']
        is_analysis_query = any(phrase in user_request.lower() for phrase in analysis_keywords)
        
        if is_analysis_query:
            logging.info(f"🎯 Detected analysis query - calling direct analysis function")
            return analyze_extreme_regions(user_request)
        
        if not python_code:
            return {
                "status": "error",
                "error": "No Python code provided",
                "user_request": user_request
            }
        
        logging.info(f"Executing custom code for: {user_request}")
        logging.info(f"Code to execute:\n{python_code}")
        
        # Set up execution environment
        exec_globals = {'__builtins__': builtins, 'builtins': builtins}
        
        # Import and setup weather tool functions
        try:
            from .weather_tool import (
                load_specific_date_kerchunk, 
                save_plot_to_blob_simple,
                get_account_key,
                find_available_kerchunk_files,
                ACCOUNT_NAME,
                VARIABLE_MAPPING,
                # ADD THESE THREE LINES:
                detect_data_source,
                find_available_spi_files,
                load_specific_month_spi_kerchunk
            )
            
            # ENHANCED: Log what functions were actually imported for debugging
            logging.info("✅ Successfully imported core weather functions:")
            logging.info(f"  - load_specific_date_kerchunk: {callable(load_specific_date_kerchunk)}")
            logging.info(f"  - save_plot_to_blob_simple: {callable(save_plot_to_blob_simple)}")
            logging.info(f"  - get_account_key: {callable(get_account_key)}")
            logging.info(f"  - ACCOUNT_NAME: {ACCOUNT_NAME}")
            
            # Get actual account key with retry logic
            max_retries = 3
            account_key = None
            for attempt in range(max_retries):
                try:
                    account_key = get_account_key()
                    logging.info("✅ Account key retrieved successfully")
                    break
                except Exception as key_error:
                    logging.warning(f"Account key retrieval attempt {attempt + 1} failed: {key_error}")
                    if attempt == max_retries - 1:
                        raise Exception(f"Failed to get account key after {max_retries} attempts: {key_error}")
                    import time
                    time.sleep(1)
            
            # Helper function for multi-day data processing (for accumulation)
            def load_and_combine_multi_day_data(start_year, start_month, start_day, num_days, variable, lat_min, lat_max, lon_min, lon_max):
                """
                Load and combine data from multiple days avoiding xarray alignment issues
                FOR ACCUMULATION ONLY - removes time dimension
                """
                import xarray as xr
                from datetime import datetime, timedelta
                
                daily_data_list = []
                
                for day_offset in range(num_days):
                    current_date = datetime(start_year, start_month, start_day) + timedelta(days=day_offset)
                    
                    try:
                        # Load data for current day
                        ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 
                                                          current_date.year, current_date.month, current_date.day)
                        
                        # Extract variable and spatial subset
                        daily_data = ds[variable].sel(
                            lat=builtins.slice(lat_min, lat_max),
                            lon=builtins.slice(lon_min, lon_max)
                        )
                        
                        # Sum over time dimension for daily accumulation
                        daily_total = daily_data.sum(dim='time')
                        
                        # Remove time coordinate to avoid alignment issues
                        daily_total = daily_total.drop_vars('time', errors='ignore')
                        
                        daily_data_list.append(daily_total)
                        ds.close()
                        
                        logging.info(f"Loaded data for {current_date.date()}")
                        
                    except Exception as e:
                        logging.warning(f"Failed to load data for {current_date.date()}: {e}")
                        continue
                
                if not daily_data_list:
                    raise Exception("No daily data could be loaded")
                
                # Sum all daily totals (now they have compatible coordinates)
                total_precipitation = sum(daily_data_list)
                
                logging.info(f"Combined {len(daily_data_list)} days of data")
                return total_precipitation

            # NEW: Helper function for time series analysis (preserves time dimension)
            def load_multi_day_time_series(start_year, start_month, start_day, num_days, variable, lat_min, lat_max, lon_min, lon_max):
                """
                Load multiple days of data preserving the time dimension for time series analysis
                """
                import xarray as xr
                from datetime import datetime, timedelta
                
                daily_datasets = []
                
                for day_offset in range(num_days):
                    current_date = datetime(start_year, start_month, start_day) + timedelta(days=day_offset)
                    
                    try:
                        # Load data for current day
                        ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 
                                                          current_date.year, current_date.month, current_date.day)
                        
                        # Extract variable and spatial subset
                        daily_data = ds[variable].sel(
                            lat=builtins.slice(lat_min, lat_max),
                            lon=builtins.slice(lon_min, lon_max)
                        )
                        
                        # Keep the dataset for concatenation (preserve time dimension)
                        daily_datasets.append(daily_data)
                        ds.close()
                        
                        logging.info(f"Loaded time series data for {current_date.date()}")
                        
                    except Exception as e:
                        logging.warning(f"Failed to load data for {current_date.date()}: {e}")
                        continue
                
                if not daily_datasets:
                    raise Exception("No daily data could be loaded")
                
                # Concatenate along time dimension to create continuous time series
                time_series_data = xr.concat(daily_datasets, dim='time')
                
                logging.info(f"Created time series with {len(daily_datasets)} days of data")
                return time_series_data

            # RESTORED: Animation function for GIFs with proper imports
            def save_animation_to_blob(animation, filename, account_key):
                """
                Save matplotlib animation to Azure Blob Storage as GIF and return URL
                """
                import matplotlib.animation as animation_module
                from PIL import Image
                import tempfile
                import os
                from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
                from datetime import datetime, timedelta
                
                try:
                    # Create temporary file for the GIF
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.gif') as tmp_file:
                        temp_gif_path = tmp_file.name
                    
                    # Save animation as GIF with optimized settings
                    writer = animation_module.PillowWriter(fps=1, bitrate=1800)
                    animation.save(temp_gif_path, writer=writer)
                    
                    # Read the GIF file
                    with open(temp_gif_path, 'rb') as gif_file:
                        gif_data = gif_file.read()
                    
                    # Upload to blob storage
                    blob_service_client = BlobServiceClient(
                        account_url=f"https://{ACCOUNT_NAME}.blob.core.windows.net",
                        credential=account_key
                    )
                    
                    container_name = "animations"
                    
                    # Create container if it doesn't exist
                    try:
                        container_client = blob_service_client.get_container_client(container_name)
                        if not container_client.exists():
                            blob_service_client.create_container(container_name)
                            logging.info(f"Created animations container")
                    except Exception as container_error:
                        logging.warning(f"Container warning: {container_error}")
                    
                    blob_client = blob_service_client.get_blob_client(
                        container=container_name, 
                        blob=filename
                    )
                    
                    # Upload the GIF
                    blob_client.upload_blob(gif_data, overwrite=True)
                    
                    # Generate SAS URL (valid for 24 hours)
                    sas_token = generate_blob_sas(
                        account_name=ACCOUNT_NAME,
                        container_name=container_name,
                        blob_name=filename,
                        account_key=account_key,
                        permission=BlobSasPermissions(read=True),
                        expiry=datetime.utcnow() + timedelta(hours=24)
                    )
                    
                    blob_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net/{container_name}/{filename}?{sas_token}"
                    
                    # Clean up temporary file
                    try:
                        os.unlink(temp_gif_path)
                    except:
                        pass
                    
                    logging.info(f"Animation saved to: {blob_url}")
                    return blob_url
                    
                except Exception as e:
                    # Clean up temporary file on error
                    try:
                        if 'temp_gif_path' in locals():
                            os.unlink(temp_gif_path)
                    except:
                        pass
                    raise Exception(f"Failed to save animation to blob storage: {str(e)}")

            # FIXED: Multi-day animation function with proper Cartopy support
            def create_multi_day_animation(start_year, start_month, start_day, num_days, variable_name, lat_min, lat_max, lon_min, lon_max, region_name="Region"):
                """
                Create an animated GIF showing daily accumulated data over multiple days
                FIXED: Now uses proper Cartopy projection with geographic features
                """
                import matplotlib.animation as animation_module
                from datetime import datetime, timedelta
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                import numpy as np
                
                logging.info(f"🎬 Creating {num_days}-day animation for {variable_name} with Cartopy features")
                
                daily_data_list = []
                daily_dates = []
                
                # Load data for each day (unchanged)
                for day_offset in range(num_days):
                    current_date = datetime(start_year, start_month, start_day) + timedelta(days=day_offset)
                    
                    try:
                        logging.info(f"📅 Loading day {day_offset + 1}/{num_days}: {current_date.date()}")
                        
                        ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 
                                                          current_date.year, current_date.month, current_date.day)
                        
                        daily_data = ds[variable_name].sel(
                            lat=builtins.slice(lat_min, lat_max),
                            lon=builtins.slice(lon_min, lon_max)
                        )
                        
                        if variable_name == 'Rainf':
                            daily_accumulated = daily_data.sum(dim='time')
                        else:
                            daily_accumulated = daily_data.mean(dim='time')
                            if variable_name == 'Tair':
                                daily_accumulated = daily_accumulated - 273.15
                        
                        daily_data_list.append(daily_accumulated)
                        daily_dates.append(current_date)
                        ds.close()
                        
                        logging.info(f"✅ Loaded {current_date.date()}")
                        
                    except Exception as e:
                        logging.warning(f"⚠️ Failed to load data for {current_date.date()}: {e}")
                        continue
                
                if not daily_data_list:
                    raise Exception("No daily data could be loaded for animation")
                
                logging.info(f"📊 Successfully loaded {len(daily_data_list)} days of data")
                
                # FIXED: Calculate color scale with proper NaN handling
                all_values = []
                for data in daily_data_list:
                    # Filter out NaN values before adding to the list
                    valid_values = data.values[~np.isnan(data.values)]
                    if len(valid_values) > 0:
                        all_values.extend(valid_values.flatten())
                
                if len(all_values) == 0:
                    raise Exception("No valid (non-NaN) data found for animation")
                
                # Calculate color scale from valid values only
                vmin, vmax = np.min(all_values), np.max(all_values)
                
                # Add small buffer if min and max are too close
                if abs(vmax - vmin) < 0.1:
                    center = (vmin + vmax) / 2
                    vmin = center - 0.5
                    vmax = center + 0.5
                
                logging.info(f"🎨 Color scale (NaN-filtered): {vmin:.2f} to {vmax:.2f}")
                
                # FIXED: Create animation with Cartopy projection
                fig = plt.figure(figsize=(12, 10))
                fig.patch.set_facecolor('white')  # CRITICAL: White figure background
                ax = fig.add_subplot(111, projection=ccrs.PlateCarree())  # FIXED: Use Cartopy projection
                
                # CRITICAL: Version-compatible background removal for Cartopy
                try:
                    ax.background_patch.set_visible(False)
                except AttributeError:
                    try:
                        ax.outline_patch.set_visible(False)
                    except AttributeError:
                        pass
                
                cbar_created = False
                
                # FIXED: Animation function with proper Cartopy features
                def animate(frame):
                    nonlocal cbar_created
                    ax.clear()
                    
                    data = daily_data_list[frame]
                    date = daily_dates[frame]
                    
                    # Plot data with Cartopy transform
                    if variable_name == 'Rainf':
                        colormap = 'Blues'
                        unit_label = 'Accumulated Precipitation (mm)'
                    else:
                        colormap = 'coolwarm'
                        if variable_name == 'Tair':
                            unit_label = f'Temperature (°C)'
                        else:
                            unit_label = f'{variable_name} Average'
                    
                    # FIXED: Plot with Cartopy transform using calculated vmin/vmax
                    im = ax.pcolormesh(data.lon, data.lat, data.values, 
                                      cmap=colormap, vmin=vmin, vmax=vmax, 
                                      shading='auto', transform=ccrs.PlateCarree())
                    
                    # FIXED: Add proper Cartopy geographic features
                    ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='black', facecolor='none', alpha=0.7)
                    ax.add_feature(cfeature.BORDERS, linewidth=0.6, edgecolor='darkgray', facecolor='none', alpha=0.8)
                    ax.add_feature(cfeature.STATES, linewidth=0.4, edgecolor='gray', facecolor='none', alpha=0.6)
                    
                    # FIXED: Add Cartopy gridlines
                    gl = ax.gridlines(draw_labels=True, alpha=0.3, linestyle='--', linewidth=0.5)
                    gl.top_labels = False
                    gl.right_labels = False
                    gl.left_labels = True
                    gl.bottom_labels = True
                    
                    # Set extent for proper Cartopy display
                    try:
                        ax.set_extent([data.lon.min(), data.lon.max(), 
                                     data.lat.min(), data.lat.max()], 
                                     crs=ccrs.PlateCarree())
                    except:
                        pass
                    
                    # Add colorbar only once
                    if not cbar_created:
                        cbar = fig.colorbar(im, ax=ax, shrink=0.8)
                        cbar.set_label(unit_label, fontsize=16)
                        cbar_created = True
                    
                    # Set title - FIXED: Use ax.set_title for Cartopy
                    ax.set_title(f'{region_name} {unit_label}\n{date.strftime("%Y-%m-%d")}', 
                                fontsize=16, fontweight='bold')
                    
                    return [im]
                
                # Create animation (unchanged)
                try:
                    anim = animation_module.FuncAnimation(
                        fig, animate, 
                        frames=len(daily_data_list), 
                        interval=1500,
                        blit=False,
                        repeat=True
                    )
                    
                    logging.info(f"✅ Created Cartopy animation with {len(daily_data_list)} frames and geographic features")
                    return anim, fig
                    
                except Exception as anim_error:
                    logging.error(f"❌ Animation creation failed: {anim_error}")
                    plt.close(fig)
                    raise Exception(f"Animation creation failed: {str(anim_error)}")

            # NEW: SPI Multi-Year Animation Function
            def create_spi_multi_year_animation(start_year, end_year, month, lat_min, lat_max, lon_min, lon_max, region_name="Region"):
                """
                Create an animated GIF showing SPI for the same month across multiple years
                Example: May SPI from 2010-2020 to show drought trends over time
                """
                import matplotlib.animation as animation_module
                from datetime import datetime
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                
                logging.info(f"🎬 Creating SPI animation for {month:02d}/{start_year}-{end_year} ({end_year-start_year+1} years)")
                
                spi_data_list = []
                years_list = []
                month_name = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month-1]
                
                # Load SPI data for each year
                for year in range(start_year, end_year + 1):
                    try:
                        logging.info(f"📅 Loading {month_name} {year} SPI data...")
                        
                        ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, month)
                        
                        spi_data = ds['SPI3'].sel(
                            latitude=builtins.slice(lat_min, lat_max),
                            longitude=builtins.slice(lon_min, lon_max)
                        )
                        
                        # Squeeze out extra dimensions
                        if hasattr(spi_data, 'squeeze'):
                            spi_data = spi_data.squeeze()
                        
                        spi_data_list.append(spi_data)
                        years_list.append(year)
                        ds.close()
                        
                        logging.info(f"✅ Loaded {month_name} {year}")
                        
                    except Exception as e:
                        logging.warning(f"⚠️ Failed to load {month_name} {year}: {e}")
                        continue
                
                if not spi_data_list:
                    raise Exception(f"No SPI data could be loaded for {month_name} {start_year}-{end_year}")
                
                logging.info(f"📊 Successfully loaded {len(spi_data_list)} years of {month_name} SPI data")
                
                # Create animation with Cartopy projection
                fig = plt.figure(figsize=(14, 12))  # Increased height for note
                fig.patch.set_facecolor('white')
                ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
                
                # Background removal
                try:
                    ax.background_patch.set_visible(False)
                except AttributeError:
                    try:
                        ax.outline_patch.set_visible(False)
                    except AttributeError:
                        pass
                
                cbar_created = False
                
                # Animation function for SPI
                def animate(frame):
                    nonlocal cbar_created
                    ax.clear()
                    
                    data = spi_data_list[frame]
                    year = years_list[frame]
                    
                    # FIXED: Use coolwarm_r (reversed coolwarm) for SPI 
                    # This gives: blue for positive SPI (wet), red for negative SPI (drought)
                    im = ax.pcolormesh(data.longitude, data.latitude, data.values, 
                                      cmap='coolwarm_r', vmin=-2.5, vmax=2.5, 
                                      shading='auto', transform=ccrs.PlateCarree())
                    
                    # Add geographic features
                    ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='black', facecolor='none', alpha=0.7)
                    ax.add_feature(cfeature.BORDERS, linewidth=0.6, edgecolor='darkgray', facecolor='none', alpha=0.8)
                    ax.add_feature(cfeature.STATES, linewidth=0.4, edgecolor='gray', facecolor='none', alpha=0.6)
                    
                    # Add gridlines
                    gl = ax.gridlines(draw_labels=True, alpha=0.3, linestyle='--', linewidth=0.5)
                    gl.top_labels = False
                    gl.right_labels = False
                    gl.left_labels = True
                    gl.bottom_labels = True
                    
                    # Set extent
                    try:
                        ax.set_extent([data.longitude.min(), data.longitude.max(), 
                                     data.latitude.min(), data.latitude.max()], 
                                     crs=ccrs.PlateCarree())
                    except:
                        pass
                    
                    # Add colorbar only once
                    if not cbar_created:
                        cbar = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.05)
                        cbar.set_label('Standardized Precipitation Index (SPI)', fontsize=14, fontweight='bold')
                        cbar.set_ticks([-2, -1, 0, 1, 2])
                        cbar.set_ticklabels(['-2', '-1', '0', '1', '2'])
                        cbar.ax.tick_params(labelsize=12)
                        cbar_created = True
                    
                    # Dynamic title showing year and trend context
                    ax.set_title(f'{region_name} SPI - {month_name} {year}\n' +
                                f'Drought Conditions Across {end_year-start_year+1} Years ({start_year}-{end_year})', 
                                fontsize=16, fontweight='bold', pad=20)
                    
                    return [im]
                
                # NEW: Add SPI category explanation at bottom of animation
                note_text = ("SPI Categories: Extreme Drought (≤ -2.0, Red) • Severe Drought (-2.0 to -1.5) • " +
                           "Moderate Drought (-1.5 to -1.0) • Mild Drought (-1.0 to -0.5) • " +
                           "Near Normal (-0.5 to 0.5, White) • Mild Wet (0.5 to 1.0) • " +
                           "Moderate Wet (1.0 to 1.5) • Severe Wet (1.5 to 2.0) • Extreme Wet (≥ 2.0, Blue)")
                
                fig.text(0.5, 0.02, note_text, ha='center', va='bottom', fontsize=16, 
                        fontweight='bold', wrap=True, bbox=dict(boxstyle='round,pad=0.5', 
                        facecolor='lightgray', alpha=0.8))
                
                # Adjust layout to accommodate note
                plt.subplots_adjust(bottom=0.12)
                
                # Create animation
                try:
                    anim = animation_module.FuncAnimation(
                        fig, animate, 
                        frames=len(spi_data_list), 
                        interval=2000,  # 2 seconds per frame for better viewing
                        blit=False,
                        repeat=True
                    )
                    
                    logging.info(f"✅ Created SPI multi-year animation with {len(spi_data_list)} frames")
                    return anim, fig
                    
                except Exception as anim_error:
                    logging.error(f"❌ SPI animation creation failed: {anim_error}")
                    plt.close(fig)
                    raise Exception(f"SPI animation creation failed: {str(anim_error)}")

            # ENHANCED: Add SPI visualization function with drought categories
            def create_spi_map_with_categories(lon_data, lat_data, data_values, title, region_name=None):
                """
                Create SPI map with standardized scale and drought category labels
                """
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                import matplotlib.pyplot as plt
                import numpy as np
                
                # Squeeze data if needed
                if hasattr(data_values, 'squeeze'):
                    data_values = data_values.squeeze()
                elif isinstance(data_values, np.ndarray) and data_values.ndim > 2:
                    data_values = np.squeeze(data_values)
                
                fig = plt.figure(figsize=(14, 12))  # Increased height for note
                fig.patch.set_facecolor('white')
                ax = plt.axes(projection=ccrs.PlateCarree())
                
                # Background removal
                try:
                    ax.background_patch.set_visible(False)
                except AttributeError:
                    try:
                        ax.outline_patch.set_visible(False)
                    except AttributeError:
                        pass
                
                # REVERTED: Back to RdBu for single SPI maps (red=drought, blue=wet)
                im = ax.pcolormesh(lon_data, lat_data, data_values, 
                                  cmap='RdBu', shading='auto', 
                                  transform=ccrs.PlateCarree(), 
                                  vmin=-2.5, vmax=2.5)
                
                # Geographic features
                ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='black', facecolor='none', alpha=0.8)
                ax.add_feature(cfeature.BORDERS, linewidth=0.6, edgecolor='gray', facecolor='none', alpha=0.7)
                ax.add_feature(cfeature.STATES, linewidth=0.4, edgecolor='darkgray', facecolor='none', alpha=0.6)
                
                # CLEAN: Simple colorbar with just numbers
                cbar = plt.colorbar(im, ax=ax, shrink=0.8, pad=0.05)
                cbar.set_label('Standardized Precipitation Index (SPI)', fontsize=14, fontweight='bold')
                
                # CLEAN: Use meaningful ticks for SPI range
                cbar.set_ticks([-2, -1, 0, 1, 2])
                cbar.set_ticklabels(['-2', '-1', '0', '1', '2'])
                cbar.ax.tick_params(labelsize=12)
                
                # Title and gridlines
                ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
                
                gl = ax.gridlines(draw_labels=True, alpha=0.3, linestyle='--', linewidth=0.5)
                gl.top_labels = False
                gl.right_labels = False
                
                # Set extent
                try:
                    ax.set_extent([lon_data.min(), lon_data.max(), 
                                  lat_data.min(), lat_data.max()], 
                                  crs=ccrs.PlateCarree())
                except:
                    pass
                
                # ENHANCED: Updated note to reflect correct color scheme
                note_text = ("SPI Categories: Extreme Drought (≤ -2.0, Red) • Severe Drought (-2.0 to -1.5) • " +
                           "Moderate Drought (-1.5 to -1.0) • Mild Drought (-1.0 to -0.5) • " +
                           "Near Normal (-0.5 to 0.5, White) • Mild Wet (0.5 to 1.0) • " +
                           "Moderate Wet (1.0 to 1.5) • Severe Wet (1.5 to 2.0) • Extreme Wet (≥ 2.0, Blue)")
                
                fig.text(0.5, 0.02, note_text, ha='center', va='bottom', fontsize=18, 
                        fontweight='bold', wrap=True, bbox=dict(boxstyle='round,pad=0.5', 
                        facecolor='lightgray', alpha=0.8))
                
                # Adjust layout to accommodate note
                plt.subplots_adjust(bottom=0.12)
                
                return fig, ax

            # MISSING FUNCTION: Add the city labels function
            def add_city_labels_for_region(ax, extent, region_name=None):
                """
                Add city labels based on the map extent and region
                ENHANCED: Better positioning, water bodies, works for ALL variables
                """
                try:
                    import cartopy.crs as ccrs
                    
                    # Define major cities by region with coordinates
                    city_database = {
                        'california': [
                            ('Los Angeles', -118.2, 34.1),
                            ('San Francisco', -122.4, 37.8),
                            ('San Diego', -117.2, 32.7),
                            ('Sacramento', -121.5, 38.6),
                            ('Fresno', -119.8, 36.7)
                        ],
                        'florida': [
                            ('Miami', -80.2, 25.8),
                            ('Tampa', -82.5, 27.9),
                            ('Orlando', -81.4, 28.5),
                            ('Jacksonville', -81.7, 30.3),
                            ('Tallahassee', -84.3, 30.4)
                        ],
                        'maryland': [
                            ('Baltimore', -76.6, 39.3),
                            ('Annapolis', -76.5, 38.9),
                            ('Frederick', -77.4, 39.4),
                            ('Rockville', -77.2, 39.1)
                        ],
                        'alaska': [
                            ('Anchorage', -149.9, 61.2),
                            ('Fairbanks', -147.7, 64.8),
                            ('Juneau', -134.4, 58.3),
                            ('Nome', -165.4, 64.5)
                        ],
                        'michigan': [
                            ('Detroit', -83.0, 42.3),
                            ('Grand Rapids', -85.7, 42.9),
                            ('Lansing', -84.6, 42.4),
                            ('East Lansing', -84.5, 42.7),
                            ('Ann Arbor', -83.7, 42.3)
                        ]
                    }
                    
                    # Get extent bounds
                    lon_min, lon_max, lat_min, lat_max = extent
                    
                    # Fixed small offset
                    lon_offset = 0.3
                    lat_offset = 0.1
                    
                    logging.info(f"🏙️ City labeling for region: '{region_name}'")
                    
                    # Select cities to show
                    cities_to_show = []
                    
                    if region_name:
                        region_key = region_name.lower().strip()
                        if region_key in city_database:
                            cities_to_show = city_database[region_key]
                    else:
                        # Auto-detect based on extent
                        all_cities = []
                        for region_cities in city_database.values():
                            all_cities.extend(region_cities)
                        
                        for city, lon, lat in all_cities:
                            if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                                cities_to_show.append((city, lon, lat))
                    
                    # Add city markers and labels
                    cities_added = 0
                    for city_name, lon, lat in cities_to_show:
                        if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                            try:
                                # City marker
                                ax.plot(lon, lat, 'o', markersize=10, 
                                       color='red', markeredgecolor='white', 
                                       markeredgewidth=3, transform=ccrs.PlateCarree(), zorder=15)
                                
                                # City label
                                label_lon = lon + lon_offset
                                label_lat = lat + lat_offset
                                
                                ax.text(label_lon, label_lat, city_name, 
                                       transform=ccrs.PlateCarree(),
                                       fontsize=13, fontweight='bold', color='black',
                                       bbox=dict(boxstyle='round,pad=0.3', 
                                                facecolor='white', alpha=0.95, 
                                                edgecolor='black', linewidth=1.5),
                                       horizontalalignment='left', verticalalignment='bottom',
                                       zorder=19)
                                
                                cities_added += 1
                                logging.info(f"   ✅ Added city: {city_name}")
                                
                            except Exception as city_error:
                                logging.error(f"   ❌ Failed to add city {city_name}: {city_error}")
                    
                    if cities_added > 0:
                        logging.info(f"✅ Successfully added {cities_added} cities")
                    else:
                        logging.warning(f"⚠️ No cities added for region '{region_name}'")
                        
                except Exception as e:
                    logging.error(f"⚠️ City labels failed: {e}")

            # MISSING FUNCTION: Add the cartopy map function
            def create_cartopy_map(lon_data, lat_data, data_values, title, colorbar_label, cmap='viridis', figsize=(12, 8), region_name=None, show_cities=False):
                """
                Create a proper Cartopy map with geographic features
                FIXED: Now includes background removal and handles extra dimensions
                """
                try:
                    import cartopy.crs as ccrs
                    import cartopy.feature as cfeature
                    import numpy as np
                    
                    # Handle extra dimensions in data_values
                    if hasattr(data_values, 'squeeze'):
                        data_values = data_values.squeeze()
                    elif isinstance(data_values, np.ndarray) and data_values.ndim > 2:
                        data_values = np.squeeze(data_values)
                    
                    logging.info(f"Data shape after squeeze: {data_values.shape}")
                    
                    # Create figure with Cartopy projection
                    fig = plt.figure(figsize=figsize)
                    fig.patch.set_facecolor('white')
                    ax = plt.axes(projection=ccrs.PlateCarree())
                    
                    # Background removal
                    try:
                        ax.background_patch.set_visible(False)
                    except AttributeError:
                        try:
                            ax.outline_patch.set_visible(False)
                        except AttributeError:
                            pass
                    
                    # Plot the data
                    im = ax.pcolormesh(lon_data, lat_data, data_values, 
                                    cmap=cmap, shading='auto', transform=ccrs.PlateCarree())
                    
                    # Geographic features
                    ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='black', facecolor='none', alpha=0.7)
                    ax.add_feature(cfeature.BORDERS, linewidth=0.6, edgecolor='darkgray', facecolor='none', alpha=0.8)
                    ax.add_feature(cfeature.STATES, linewidth=0.4, edgecolor='gray', facecolor='none', alpha=0.6)

                    # Gridlines
                    gl = ax.gridlines(draw_labels=True, alpha=0.3, linestyle='--', linewidth=0.5)
                    gl.top_labels = False
                    gl.right_labels = False
                    gl.left_labels = True
                    gl.bottom_labels = True
                    
                    # Add colorbar
                    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
                    cbar.set_label(colorbar_label, fontsize=16)
                    
                    # Set title
                    ax.set_title(title, fontsize=16, fontweight='bold')
                    
                    # Set extent
                    try:
                        ax.set_extent([lon_data.min(), lon_data.max(), 
                                    lat_data.min(), lat_data.max()], 
                                    crs=ccrs.PlateCarree())
                    except:
                        pass
                    
                    # Add city labels if requested
                    if show_cities or region_name:
                        try:
                            extent = [float(lon_data.min()), float(lon_data.max()),
                                      float(lat_data.min()), float(lat_data.max())]
                            add_city_labels_for_region(ax, extent, region_name)
                        except Exception as label_err:
                            logging.warning(f"City labeling skipped: {label_err}")
                    
                    logging.info("✅ Created Cartopy map with geographic features")
                    return fig, ax
                    
                except ImportError:
                    logging.error("❌ Cartopy not available")
                    raise ImportError("Cartopy is required for proper geographic maps")
                except Exception as e:
                    logging.error(f"❌ Cartopy map creation failed: {e}")
                    raise Exception(f"Failed to create Cartopy map: {str(e)}")

            # MISSING FUNCTION: Add the cartopy map with cities function
            def create_cartopy_map_with_cities(lon_data, lat_data, data_values, title, colorbar_label, cmap='viridis', figsize=(12, 8), region_name=None):
                """
                Create a Cartopy map with geographic features AND city labels
                """
                return create_cartopy_map(lon_data, lat_data, data_values, title, colorbar_label, cmap, figsize, region_name, show_cities=True)

            # Add ALL functions to execution environment - ENHANCED LOGGING
            core_functions = {
                # Basic weather functions
                'load_specific_date_kerchunk': load_specific_date_kerchunk,
                'save_plot_to_blob_simple': save_plot_to_blob_simple,
                'get_account_key': get_account_key,
                'find_available_kerchunk_files': find_available_kerchunk_files,
                'ACCOUNT_NAME': ACCOUNT_NAME,
                'account_key': account_key,
                'VARIABLE_MAPPING': VARIABLE_MAPPING,
                # ADD THESE THREE LINES:
                'detect_data_source': detect_data_source,
                'find_available_spi_files': find_available_spi_files,
                'load_specific_month_spi_kerchunk': load_specific_month_spi_kerchunk,
            }
            
            # Log each core function
            for name, func in core_functions.items():
                if callable(func):
                    logging.info(f"✅ Adding function to exec_globals: {name}")
                else:
                    logging.info(f"✅ Adding variable to exec_globals: {name} = {func}")
            
            exec_globals.update(core_functions)
            
            # Add multi-day and other functions
            exec_globals.update({
                # Multi-day data functions
                'load_and_combine_multi_day_data': load_and_combine_multi_day_data,
                'load_multi_day_time_series': load_multi_day_time_series,
                
                # ENHANCED: Animation functions with geographic features
                'save_animation_to_blob': save_animation_to_blob,
                'create_multi_day_animation': create_multi_day_animation,
                'add_city_labels_for_region': add_city_labels_for_region,
                
                # CRITICAL FIX: Add the MISSING create_cartopy_map functions
                'create_cartopy_map': create_cartopy_map,
                'create_cartopy_map_with_cities': create_cartopy_map_with_cities,
                # NEW: Add enhanced SPI visualization
                'create_spi_map_with_categories': create_spi_map_with_categories,
                # NEW: Add SPI multi-year animation
                'create_spi_multi_year_animation': create_spi_multi_year_animation,
            })
            
            logging.info(f"Weather functions loaded successfully. Total functions in exec_globals: {len([k for k, v in exec_globals.items() if callable(v)])}")
            
        except ImportError as import_error:
            logging.error(f"❌ IMPORT ERROR: {import_error}")
            logging.error(f"❌ Failed to import: {import_error.name if hasattr(import_error, 'name') else 'unknown'}")
            
            # Check what's actually available in weather_tool
            try:
                import agents.weather_tool as wt
                available_functions = [name for name in dir(wt) if not name.startswith('_')]
                logging.error(f"❌ Available functions in weather_tool: {available_functions}")
            except Exception as check_error:
                logging.error(f"❌ Could not check weather_tool contents: {check_error}")
            
            return {
                "status": "error",
                "error": f"Failed to import weather functions: {str(import_error)}",
                "user_request": user_request
            }
        except Exception as e:
            logging.error(f"Failed to import weather functions: {e}")
            return {
                "status": "error",
                "error": f"Failed to load weather functions: {str(e)}",
                "user_request": user_request
            }
        
        # Import data science libraries
        try:
            import pandas as pd
            import numpy as np
            import xarray as xr
            import matplotlib
            import matplotlib.pyplot as plt
            from datetime import datetime, timedelta
            import io
            import time
            
            # Set matplotlib backend
            matplotlib.use('Agg')
            
            # ENHANCED: Import Cartopy for mapping with error handling (RESTORED)
            cartopy_available = False
            try:
                import cartopy
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                cartopy_available = True
                logging.info("✅ Cartopy imported successfully for mapping")
            except ImportError as cartopy_error:
                logging.warning(f"⚠️ Cartopy not available: {cartopy_error}")
                # Create dummy objects to prevent NameError
                class DummyCRS:
                    @staticmethod
                    def PlateCarree():
                        raise ImportError("Cartopy not available - use matplotlib plotting instead")
                
                class DummyFeature:
                    COASTLINE = None
                    BORDERS = None
                    STATES = None
                
                ccrs = DummyCRS()
                cfeature = DummyFeature()
            
            # GLOBAL FONT SIZE CONFIGURATION - ALL TEXT AT 16PT
            plt.rcParams.update({
                'font.size': 16,          # FIXED: Base font size
                'axes.titlesize': 16,     # FIXED: Title font size
                'axes.labelsize': 16,     # FIXED: Axis label font size
                'xtick.labelsize': 16,    # FIXED: X-axis tick label size
                'ytick.labelsize': 16,    # FIXED: Y-axis tick label size
                'legend.fontsize': 16,    # FIXED: Legend font size
                'figure.titlesize': 16,   # FIXED: Figure title size
                'axes.titlepad': 20,      # Add padding for titles
                'axes.labelpad': 10       # Add padding for labels
            })
            
            exec_globals.update({
                'pd': pd, 'pandas': pd,
                'np': np, 'numpy': np,
                'xr': xr, 'xarray': xr,
                'plt': plt, 'matplotlib': matplotlib,
                'datetime': datetime, 'timedelta': timedelta,
                'io': io,
                'time': time,
                'logging': logging,
                # RESTORED: Cartopy imports to execution environment
                'cartopy': cartopy if cartopy_available else None,
                'ccrs': ccrs,
                'cfeature': cfeature,
                'cartopy_available': cartopy_available,
            })
            
            logging.info(f"Libraries loaded successfully with 16pt font configuration. Cartopy available: {cartopy_available}")
            
        except Exception as e:
            logging.error(f"Failed to import libraries: {e}")
            return {
                "status": "error",
                "error": f"Failed to load libraries: {str(e)}",
                "user_request": user_request
            }
        
        # Execute the code
        try:
            exec_locals = {}
            
            # Add better error debugging
            logging.info("=" * 50)
            logging.info("EXECUTING PYTHON CODE:")
            logging.info("=" * 50)
            logging.info(python_code)
            logging.info("=" * 50)
            
            # Check for obvious syntax issues before execution
            try:
                compile(python_code, '<string>', 'exec')
                logging.info("✅ Code syntax validation passed")
            except SyntaxError as syntax_error:
                logging.error(f"❌ SYNTAX ERROR DETECTED BEFORE EXECUTION:")
                logging.error(f"   Line {syntax_error.lineno}: {syntax_error.text}")
                logging.error(f"   Error: {syntax_error.msg}")
                raise syntax_error
            
            # ENHANCED: Log available functions in exec_globals for debugging
            available_functions = [key for key in exec_globals.keys() if callable(exec_globals[key])]
            logging.info(f"📋 Available functions: {available_functions}")
            
            exec(python_code, exec_globals, exec_locals)
            
            # Get result and ensure it's JSON serializable
            result = exec_locals.get('result', 'No result variable found')
            
            # Convert numpy arrays and other non-serializable types
            def make_serializable(obj):
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.bool_):
                    return bool(obj)
                elif isinstance(obj, dict):
                    return {k: make_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [make_serializable(item) for item in obj]
                else:
                    return obj
            
            # Make result JSON serializable
            result = make_serializable(result)
            
            logging.info(f"Code executed successfully. Result type: {type(result)}")
            if isinstance(result, (int, float, str, dict, list)):
                logging.info(f"Result value: {result}")
            
            return {
                "status": "success",
                "result": result,
                "python_code": python_code,
                "user_request": user_request
            }
            
        except Exception as e:
            error_msg = str(e)
            traceback_str = traceback.format_exc()
            
            logging.error(f"Code execution failed: {error_msg}")
            logging.error(f"Full traceback: {traceback_str}")
            
            return {
                "status": "error",
                "error": f"Code execution failed: {error_msg}",
                "traceback": traceback_str[-500:],  # Last 500 chars of traceback
                "python_code": python_code,
                "user_request": user_request
            }
            
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Function setup failed: {error_msg}")
        
        return {
            "status": "error",
            "error": f"Function setup failed: {error_msg}",
            "user_request": args.get("user_request", "Unknown")
        }