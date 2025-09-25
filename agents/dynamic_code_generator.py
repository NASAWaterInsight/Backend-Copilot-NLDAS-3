import json
import logging
import traceback
import builtins

def execute_custom_code(args: dict):
    """
    Execute custom Python code with proper NLDAS-3 environment setup
    """
    try:
        user_request = args.get("user_request", "Unknown request")
        python_code = args.get("python_code", "")
        
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
                save_plot_to_blob_simple,  # Make sure this is imported
                get_account_key,
                find_available_kerchunk_files,
                ACCOUNT_NAME,
                VARIABLE_MAPPING
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
                
                # Calculate color scale (unchanged)
                all_values = []
                for data in daily_data_list:
                    all_values.extend(data.values.flatten())
                vmin, vmax = min(all_values), max(all_values)
                
                logging.info(f"🎨 Color scale: {vmin:.2f} to {vmax:.2f}")
                
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
                        colormap = 'RdYlBu_r'
                        if variable_name == 'Tair':
                            unit_label = f'Temperature (°C)'
                        else:
                            unit_label = f'{variable_name} Average'
                    
                    # FIXED: Plot with Cartopy transform
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

            # ENHANCED: Updated dual variable animation with Cartopy
            def create_dual_variable_animation(start_year, start_month, start_day, num_days, lat_min, lat_max, lon_min, lon_max, region_name="Region"):
                """
                Create dual-variable animation with proper Cartopy projections
                FIXED: Both subplots now use Cartopy with geographic features
                """
                import matplotlib.animation as animation_module
                from datetime import datetime, timedelta
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                
                logging.info(f"🎬 Creating dual-variable Cartopy animation for {num_days} days")
                
                daily_temp_list = []
                daily_precip_list = []
                daily_dates = []
                
                # Load data (unchanged)
                for day_offset in range(num_days):
                    current_date = datetime(start_year, start_month, start_day) + timedelta(days=day_offset)
                    
                    try:
                        ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 
                                                          current_date.year, current_date.month, current_date.day)
                        
                        temp_data = ds['Tair'].sel(
                            lat=builtins.slice(lat_min, lat_max),
                            lon=builtins.slice(lon_min, lon_max)
                        ).mean(dim='time') - 273.15
                        
                        precip_data = ds['Rainf'].sel(
                            lat=builtins.slice(lat_min, lat_max),
                            lon=builtins.slice(lon_min, lon_max)
                        ).sum(dim='time')
                        
                        daily_temp_list.append(temp_data)
                        daily_precip_list.append(precip_data)
                        daily_dates.append(current_date)
                        ds.close()
                        
                    except Exception as e:
                        logging.warning(f"⚠️ Failed to load data for {current_date.date()}: {e}")
                        continue
                
                if not daily_temp_list or not daily_precip_list:
                    raise Exception("No daily data could be loaded for dual animation")
                
                # FIXED: Create figure with Cartopy subplots
                fig = plt.figure(figsize=(20, 8))
                fig.patch.set_facecolor('white')
                
                # FIXED: Create Cartopy subplots
                ax1 = fig.add_subplot(1, 2, 1, projection=ccrs.PlateCarree())
                ax2 = fig.add_subplot(1, 2, 2, projection=ccrs.PlateCarree())
                
                # CRITICAL: Background removal for BOTH Cartopy subplots
                for ax in [ax1, ax2]:
                    try:
                        ax.background_patch.set_visible(False)
                    except AttributeError:
                        try:
                            ax.outline_patch.set_visible(False)
                        except AttributeError:
                            pass
                
                # Calculate color ranges (unchanged)
                temp_values = []
                precip_values = []
                for temp, precip in zip(daily_temp_list, daily_precip_list):
                    temp_values.extend(temp.values.flatten())
                    precip_values.extend(precip.values.flatten())
                
                temp_vmin, temp_vmax = min(temp_values), max(temp_values)
                precip_vmin, precip_vmax = min(precip_values), max(precip_values)
                
                # FIXED: Animation function with Cartopy features
                def animate_dual(frame):
                    ax1.clear()
                    ax2.clear()
                    
                    temp_data = daily_temp_list[frame]
                    precip_data = daily_precip_list[frame]
                    date = daily_dates[frame]
                    
                    # FIXED: Plot with Cartopy transforms
                    im1 = ax1.pcolormesh(temp_data.lon, temp_data.lat, temp_data.values, 
                                        cmap='RdYlBu_r', vmin=temp_vmin, vmax=temp_vmax, 
                                        shading='auto', transform=ccrs.PlateCarree())
                    
                    im2 = ax2.pcolormesh(precip_data.lon, precip_data.lat, precip_data.values,
                                        cmap='Blues', vmin=precip_vmin, vmax=precip_vmax, 
                                        shading='auto', transform=ccrs.PlateCarree())
                    
                    # FIXED: Add Cartopy geographic features to BOTH subplots
                    for ax in [ax1, ax2]:
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
                            ax.set_extent([temp_data.lon.min(), temp_data.lon.max(), 
                                         temp_data.lat.min(), temp_data.lat.max()], 
                                         crs=ccrs.PlateCarree())
                        except:
                            pass
                    
                    # Titles
                    ax1.set_title(f'{region_name} Temperature\n{date.strftime("%Y-%m-%d")}', fontsize=16)
                    ax2.set_title(f'{region_name} Precipitation\n{date.strftime("%Y-%m-%d")}', fontsize=16)
                    
                    # Colorbars (only on first frame)
                    if frame == 0:
                        cbar1 = fig.colorbar(im1, ax=ax1, shrink=0.8)
                        cbar1.set_label('Temperature (°C)', fontsize=16)
                        
                        cbar2 = fig.colorbar(im2, ax=ax2, shrink=0.8)
                        cbar2.set_label('Precipitation (mm)', fontsize=16)
                    
                    return [im1, im2]
                
                # Create animation
                anim = animation_module.FuncAnimation(
                    fig, animate_dual,
                    frames=len(daily_temp_list),
                    interval=1500,
                    blit=False,
                    repeat=True
                )
                
                logging.info(f"✅ Created dual-variable Cartopy animation with {len(daily_temp_list)} frames and geographic features")
                return anim, fig

            def add_city_labels_for_region(ax, extent, region_name=None):
                """
                Add city labels based on the map extent and region
                ENHANCED: Better positioning, water bodies, works for ALL variables
                """
                try:
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
                    
                    # NEW: Water bodies database (lakes, bays, etc.)
                    water_bodies_database = {
                        'california': [
                            ('San Francisco Bay', -122.3, 37.7),
                            ('Lake Tahoe', -120.0, 39.1),
                            ('Salton Sea', -115.8, 33.3)
                        ],
                        'florida': [
                            ('Tampa Bay', -82.6, 27.8),
                            ('Biscayne Bay', -80.2, 25.6),
                            ('Lake Okeechobee', -80.8, 26.9),
                            ('Florida Bay', -80.9, 25.1)
                        ],
                        'maryland': [
                            ('Chesapeake Bay', -76.3, 38.8),
                            ('Potomac River', -77.0, 38.5)
                        ],
                        'alaska': [
                            ('Cook Inlet', -151.0, 60.5),
                            ('Prince William Sound', -147.0, 60.7),
                            ('Bristol Bay', -159.0, 58.5)
                        ],
                        'michigan': [
                            ('Lake Michigan', -87.0, 43.5),
                            ('Lake Huron', -83.5, 44.8),
                            ('Lake Superior', -87.5, 47.2),
                            ('Saginaw Bay', -83.8, 43.8)
                        ]
                    }
                    
                    # Get extent bounds
                    lon_min, lon_max, lat_min, lat_max = extent
                    
                    # FIXED: Much smaller, consistent offset (was too dynamic before)
                    lon_offset = 0.3  # Fixed small offset
                    lat_offset = 0.1  # Fixed small offset
                    
                    # ENHANCED: Debug logging for troubleshooting
                    logging.info(f"🏙️ City labeling request for ALL variables:")
                    logging.info(f"   Region name provided: '{region_name}'")
                    logging.info(f"   Map extent: lon {lon_min:.1f} to {lon_max:.1f}, lat {lat_min:.1f} to {lat_max:.1f}")
                    logging.info(f"   FIXED offsets: lon_offset={lon_offset}, lat_offset={lat_offset}")
                    
                    # Select cities to show
                    cities_to_show = []
                    water_bodies_to_show = []
                    
                    # FIXED: More robust region name matching
                    if region_name:
                        region_key = region_name.lower().strip()
                        logging.info(f"   Looking for region key: '{region_key}'")
                        
                        if region_key in city_database:
                            cities_to_show = city_database[region_key]
                            # NEW: Add water bodies for the region
                            water_bodies_to_show = water_bodies_database.get(region_key, [])
                            logging.info(f"   ✅ Found {len(cities_to_show)} cities and {len(water_bodies_to_show)} water bodies for {region_key}")
                        else:
                            logging.warning(f"   ❌ Region '{region_key}' not found in database")
                            logging.warning(f"   Available regions: {list(city_database.keys())}")
                    else:
                        logging.info("   No region name provided, using extent-based detection")
                        
                        # Auto-detect based on extent
                        all_cities = []
                        all_water_bodies = []
                        for region_cities in city_database.values():
                            all_cities.extend(region_cities)
                        for region_water in water_bodies_database.values():
                            all_water_bodies.extend(region_water)
                        
                        # Filter cities and water bodies within the extent
                        for city, lon, lat in all_cities:
                            if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                                cities_to_show.append((city, lon, lat))
                                logging.info(f"   📍 Auto-detected city: {city} ({lon}, {lat})")
                        
                        for water_body, lon, lat in all_water_bodies:
                            if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                                water_bodies_to_show.append((water_body, lon, lat))
                                logging.info(f"   🌊 Auto-detected water body: {water_body} ({lon}, {lat})")
                    
                    # ENHANCED: Add city markers and labels with FIXED positioning
                    cities_added = 0
                    for city_name, lon, lat in cities_to_show:
                        # DOUBLE CHECK: Ensure city is within bounds
                        if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                            try:
                                # ENHANCED: Larger, more visible city marker with double border
                                ax.plot(lon, lat, 'o', markersize=10, 
                                       color='red', markeredgecolor='white', 
                                       markeredgewidth=3, transform=ccrs.PlateCarree(), zorder=15)
                                
                                # Add inner marker for extra visibility
                                ax.plot(lon, lat, 'o', markersize=6, 
                                       color='darkred', transform=ccrs.PlateCarree(), zorder=16)
                                
                                # FIXED: Single label with SMALL, consistent offset
                                label_lon = lon + lon_offset  # Just 0.3 degrees
                                label_lat = lat + lat_offset  # Just 0.1 degrees
                                
                                # Single high-contrast label (simplified from triple-layer)
                                ax.text(label_lon, label_lat, city_name, 
                                       transform=ccrs.PlateCarree(),
                                       fontsize=13, fontweight='bold', color='black',
                                       bbox=dict(boxstyle='round,pad=0.3', 
                                                facecolor='white', alpha=0.95, 
                                                edgecolor='black', linewidth=1.5),
                                       horizontalalignment='left', verticalalignment='bottom',
                                       zorder=19)
                                
                                cities_added += 1
                                logging.info(f"   ✅ Added FIXED-position city: {city_name} at ({lon:.1f}, {lat:.1f}) -> label at ({label_lon:.1f}, {label_lat:.1f})")
                                
                            except Exception as city_error:
                                logging.error(f"   ❌ Failed to add city {city_name}: {city_error}")
                        else:
                            logging.info(f"   ⚠️ City {city_name} outside bounds: ({lon:.1f}, {lat:.1f})")
                    
                    # NEW: Add water body labels (different style)
                    water_bodies_added = 0
                    for water_name, lon, lat in water_bodies_to_show:
                        if lon_min <= lon <= lon_max and lat_min <= lat <= lat_max:
                            try:
                                # Water body marker (blue square)
                                ax.plot(lon, lat, 's', markersize=8, 
                                       color='blue', markeredgecolor='white', 
                                       markeredgewidth=2, transform=ccrs.PlateCarree(), zorder=15)
                                
                                # Water body label with blue styling
                                label_lon = lon + lon_offset
                                label_lat = lat - lat_offset  # Offset downward for water bodies
                                
                                ax.text(label_lon, label_lat, water_name, 
                                       transform=ccrs.PlateCarree(),
                                       fontsize=11, fontweight='bold', color='navy',
                                       bbox=dict(boxstyle='round,pad=0.2', 
                                                facecolor='lightblue', alpha=0.9, 
                                                edgecolor='blue', linewidth=1),
                                       horizontalalignment='left', verticalalignment='top',
                                       zorder=18)
                                
                                water_bodies_added += 1
                                logging.info(f"   🌊 Added water body: {water_name} at ({lon:.1f}, {lat:.1f})")
                                
                            except Exception as water_error:
                                logging.error(f"   ❌ Failed to add water body {water_name}: {water_error}")
                    
                    total_labels = cities_added + water_bodies_added
                    if total_labels > 0:
                        logging.info(f"✅ Successfully added {cities_added} cities + {water_bodies_added} = {total_labels} total labels")
                        logging.info(f"📍 Labels work for ALL variables (temperature, precipitation, humidity, etc.)")
                    else:
                        logging.warning(f"⚠️ No labels added! Check region name and coordinates.")
                        
                except Exception as e:
                    logging.error(f"⚠️ City/water body labels failed: {e}")
                    import traceback
                    logging.error(f"⚠️ Labels traceback: {traceback.format_exc()}")

            def create_cartopy_map_with_cities(lon_data, lat_data, data_values, title, colorbar_label, cmap='viridis', figsize=(12, 8), region_name=None):
                """
                Create a Cartopy map with geographic features AND city labels
                FIXED: Now includes the same background removal as create_cartopy_map
                """
                try:
                    import cartopy.crs as ccrs
                    import cartopy.feature as cfeature
                    
                    # Create figure with Cartopy projection
                    fig = plt.figure(figsize=figsize)
                    fig.patch.set_facecolor('white')  # CRITICAL: White figure background
                    ax = plt.axes(projection=ccrs.PlateCarree())
                    
                    # CRITICAL: Version-compatible background removal - SAME AS create_cartopy_map
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
                    
                    # CRITICAL: Use edgecolor/facecolor instead of color to prevent fills - SAME AS create_cartopy_map
                    ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='black', facecolor='none', alpha=0.7)
                    ax.add_feature(cfeature.BORDERS, linewidth=0.6, edgecolor='darkgray', facecolor='none', alpha=0.8)
                    ax.add_feature(cfeature.STATES, linewidth=0.4, edgecolor='gray', facecolor='none', alpha=0.6)
                    
                    # ADD CITY LABELS based on region
                    extent = [lon_data.min(), lon_data.max(), lat_data.min(), lat_data.max()]
                    add_city_labels_for_region(ax, extent, region_name)
                    
                    # CRITICAL: Clean gridlines - SAME AS create_cartopy_map
                    gl = ax.gridlines(draw_labels=True, alpha=0.3, linestyle='--', linewidth=0.5)
                    gl.top_labels = False
                    gl.right_labels = False
                    gl.left_labels = True
                    gl.bottom_labels = True
                    
                    # Colorbar and title
                    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
                    cbar.set_label(colorbar_label, fontsize=16)
                    ax.set_title(title, fontsize=16, fontweight='bold')
                    
                    # Set extent
                    ax.set_extent(extent, crs=ccrs.PlateCarree())
                    
                    logging.info("✅ Created Cartopy map with cities (no gray areas)")
                    return fig, ax
                    
                except Exception as e:
                    logging.error(f"❌ Cartopy map with cities failed: {e}")
                    # Fallback to regular map
                    return create_cartopy_map(lon_data, lat_data, data_values, title, colorbar_label, cmap, figsize)

            def create_cartopy_map(lon_data, lat_data, data_values, title, colorbar_label, cmap='viridis', figsize=(12, 8)):
                """
                Create a proper Cartopy map with geographic features
                FIXED: Now includes background removal to prevent gray areas
                """
                try:
                    import cartopy.crs as ccrs
                    import cartopy.feature as cfeature
                    
                    # Create figure with Cartopy projection
                    fig = plt.figure(figsize=figsize)
                    fig.patch.set_facecolor('white')  # CRITICAL: White figure background
                    ax = plt.axes(projection=ccrs.PlateCarree())
                    
                    # CRITICAL: Version-compatible background removal
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
                    
                    # CRITICAL: Use edgecolor/facecolor instead of color to prevent fills
                    ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor='black', facecolor='none', alpha=0.7)
                    ax.add_feature(cfeature.BORDERS, linewidth=0.6, edgecolor='darkgray', facecolor='none', alpha=0.8)
                    ax.add_feature(cfeature.STATES, linewidth=0.4, edgecolor='gray', facecolor='none', alpha=0.6)

                    # CRITICAL: Clean gridlines
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
                    
                    # Set extent if data bounds are available
                    try:
                        ax.set_extent([lon_data.min(), lon_data.max(), 
                                    lat_data.min(), lat_data.max()], 
                                    crs=ccrs.PlateCarree())
                    except:
                        pass
                    
                    logging.info("✅ Created Cartopy map with geographic features (no gray areas)")
                    return fig, ax
                    
                except ImportError:
                    logging.error("❌ Cartopy not available - cannot create projected map")
                    raise ImportError("Cartopy is required for proper geographic maps")
                except Exception as e:
                    logging.error(f"❌ Cartopy map creation failed: {e}")
                    raise Exception(f"Failed to create Cartopy map: {str(e)}")

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