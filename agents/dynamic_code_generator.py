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
                save_plot_to_blob_simple,
                get_account_key,
                find_available_kerchunk_files,
                ACCOUNT_NAME,
                VARIABLE_MAPPING
            )
            
            # Get actual account key with retry logic
            max_retries = 3
            account_key = None
            for attempt in range(max_retries):
                try:
                    account_key = get_account_key()
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
            
            # FIXED: Animation function for GIFs with proper imports
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

            # FIXED: Multi-day animation function with proper structure
            def create_multi_day_animation(start_year, start_month, start_day, num_days, variable_name, lat_min, lat_max, lon_min, lon_max, region_name="Region"):
                """
                Create an animated GIF showing daily accumulated data over multiple days
                """
                import matplotlib.animation as animation_module
                from datetime import datetime, timedelta
                
                logging.info(f"🎬 Creating {num_days}-day animation for {variable_name}")
                
                daily_data_list = []
                daily_dates = []
                
                # Load data for each day
                for day_offset in range(num_days):
                    current_date = datetime(start_year, start_month, start_day) + timedelta(days=day_offset)
                    
                    try:
                        logging.info(f"📅 Loading day {day_offset + 1}/{num_days}: {current_date.date()}")
                        
                        # Load data for current day
                        ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 
                                                          current_date.year, current_date.month, current_date.day)
                        
                        # Extract variable and spatial subset
                        daily_data = ds[variable_name].sel(
                            lat=builtins.slice(lat_min, lat_max),
                            lon=builtins.slice(lon_min, lon_max)
                        )
                        
                        # Sum over time for daily accumulation
                        if variable_name == 'Rainf':
                            daily_accumulated = daily_data.sum(dim='time')
                        else:
                            daily_accumulated = daily_data.mean(dim='time')
                        
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
                
                # Create the animation with FIXED structure
                fig, ax = plt.subplots(figsize=(12, 10))
                
                # Determine global color scale for consistency
                all_values = []
                for data in daily_data_list:
                    all_values.extend(data.values.flatten())
                
                vmin = min(all_values)
                vmax = max(all_values)
                
                logging.info(f"🎨 Color scale: {vmin:.2f} to {vmax:.2f}")
                
                # Store colorbar reference to avoid recreating
                cbar_created = False
                
                # FIXED Animation function with proper variable scoping
                def animate(frame):
                    nonlocal cbar_created
                    
                    # Clear the axes
                    ax.clear()
                    
                    # Get data for this frame
                    data = daily_data_list[frame]
                    date = daily_dates[frame]
                    
                    # Plot the data
                    if variable_name == 'Rainf':
                        colormap = 'Blues'
                        unit_label = 'Accumulated Precipitation (kg/m²)'
                    else:
                        colormap = 'RdYlBu_r'
                        unit_label = f'{variable_name} Average'
                    
                    # Create the plot
                    im = ax.pcolormesh(data.lon, data.lat, data.values, 
                                      cmap=colormap, vmin=vmin, vmax=vmax, shading='auto')
                    
                    # Add colorbar only once
                    if not cbar_created:
                        cbar = fig.colorbar(im, ax=ax)
                        cbar.set_label(unit_label, fontsize=16)
                        cbar_created = True
                    
                    # Set title and labels
                    ax.set_title(f'{region_name} {unit_label}\n{date.strftime("%Y-%m-%d")}', 
                                fontsize=16, fontweight='bold')
                    ax.set_xlabel('Longitude', fontsize=16)
                    ax.set_ylabel('Latitude', fontsize=16)
                    
                    return [im]
                
                # Create animation with proper parameters
                try:
                    anim = animation_module.FuncAnimation(
                        fig, animate, 
                        frames=len(daily_data_list), 
                        interval=1500,  # 1.5 seconds per frame
                        blit=False,     # Don't use blitting to avoid issues
                        repeat=True
                    )
                    
                    logging.info(f"✅ Created animation with {len(daily_data_list)} frames")
                    return anim, fig
                    
                except Exception as anim_error:
                    logging.error(f"❌ Animation creation failed: {anim_error}")
                    plt.close(fig)
                    raise Exception(f"Animation creation failed: {str(anim_error)}")

            # NEW: Simple multi-variable animation for temperature + precipitation
            def create_dual_variable_animation(start_year, start_month, start_day, num_days, lat_min, lat_max, lon_min, lon_max, region_name="Region"):
                """
                Create an animation showing both temperature and precipitation for the same region
                """
                import matplotlib.animation as animation_module
                from datetime import datetime, timedelta
                
                logging.info(f"🎬 Creating dual-variable animation for {num_days} days")
                
                daily_temp_list = []
                daily_precip_list = []
                daily_dates = []
                
                # Load data for each day
                for day_offset in range(num_days):
                    current_date = datetime(start_year, start_month, start_day) + timedelta(days=day_offset)
                    
                    try:
                        logging.info(f"📅 Loading day {day_offset + 1}/{num_days}: {current_date.date()}")
                        
                        # Load data for current day
                        ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, 
                                                          current_date.year, current_date.month, current_date.day)
                        
                        # Extract temperature data
                        temp_data = ds['Tair'].sel(
                            lat=builtins.slice(lat_min, lat_max),
                            lon=builtins.slice(lon_min, lon_max)
                        ).mean(dim='time')
                        
                        # Extract precipitation data
                        precip_data = ds['Rainf'].sel(
                            lat=builtins.slice(lat_min, lat_max),
                            lon=builtins.slice(lon_min, lon_max)
                        ).sum(dim='time')
                        
                        daily_temp_list.append(temp_data)
                        daily_precip_list.append(precip_data)
                        daily_dates.append(current_date)
                        
                        ds.close()
                        logging.info(f"✅ Loaded {current_date.date()}")
                        
                    except Exception as e:
                        logging.warning(f"⚠️ Failed to load data for {current_date.date()}: {e}")
                        continue
                
                if not daily_temp_list or not daily_precip_list:
                    raise Exception("No daily data could be loaded for dual animation")
                
                # Create figure with 2 subplots
                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))
                
                # Calculate color ranges
                temp_values = []
                precip_values = []
                for temp, precip in zip(daily_temp_list, daily_precip_list):
                    temp_values.extend(temp.values.flatten())
                    precip_values.extend(precip.values.flatten())
                
                temp_vmin, temp_vmax = min(temp_values), max(temp_values)
                precip_vmin, precip_vmax = min(precip_values), max(precip_values)
                
                # Animation function
                def animate_dual(frame):
                    # Clear both axes
                    ax1.clear()
                    ax2.clear()
                    
                    temp_data = daily_temp_list[frame]
                    precip_data = daily_precip_list[frame]
                    date = daily_dates[frame]
                    
                    # Plot temperature
                    im1 = ax1.pcolormesh(temp_data.lon, temp_data.lat, temp_data.values, 
                                        cmap='RdYlBu_r', vmin=temp_vmin, vmax=temp_vmax, shading='auto')
                    
                    # Plot precipitation  
                    im2 = ax2.pcolormesh(precip_data.lon, precip_data.lat, precip_data.values,
                                        cmap='Blues', vmin=precip_vmin, vmax=precip_vmax, shading='auto')
                    
                    # Add titles and labels
                    ax1.set_title(f'{region_name} Temperature\n{date.strftime("%Y-%m-%d")}', fontsize=16)
                    ax1.set_xlabel('Longitude', fontsize=16)
                    ax1.set_ylabel('Latitude', fontsize=16)
                    
                    ax2.set_title(f'{region_name} Precipitation\n{date.strftime("%Y-%m-%d")}', fontsize=16)
                    ax2.set_xlabel('Longitude', fontsize=16)
                    ax2.set_ylabel('Latitude', fontsize=16)
                    
                    # Add colorbars (only on first frame)
                    if frame == 0:
                        cbar1 = fig.colorbar(im1, ax=ax1)
                        cbar1.set_label('Temperature (K)', fontsize=16)
                        
                        cbar2 = fig.colorbar(im2, ax=ax2)
                        cbar2.set_label('Precipitation (kg/m²)', fontsize=16)
                    
                    return [im1, im2]
                
                # Create animation
                anim = animation_module.FuncAnimation(
                    fig, animate_dual,
                    frames=len(daily_temp_list),
                    interval=1500,
                    blit=False,
                    repeat=True
                )
                
                logging.info(f"✅ Created dual-variable animation with {len(daily_temp_list)} frames")
                return anim, fig

            # Add both helper functions to execution environment
            exec_globals.update({
                'load_specific_date_kerchunk': load_specific_date_kerchunk,
                'save_plot_to_blob_simple': save_plot_to_blob_simple,
                'get_account_key': get_account_key,
                'find_available_kerchunk_files': find_available_kerchunk_files,
                'ACCOUNT_NAME': ACCOUNT_NAME,
                'account_key': account_key,  # Real account key
                'VARIABLE_MAPPING': VARIABLE_MAPPING,
                'load_and_combine_multi_day_data': load_and_combine_multi_day_data,  # For accumulation
                'load_multi_day_time_series': load_multi_day_time_series,  # NEW: For time series
                'save_animation_to_blob': save_animation_to_blob,  # NEW: For animations
                'create_multi_day_animation': create_multi_day_animation,  # NEW: For animations
                'create_dual_variable_animation': create_dual_variable_animation,  # NEW: For dual-variable animations
            })
            
            logging.info(f"Weather functions loaded. ACCOUNT_NAME: {ACCOUNT_NAME}")
            
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
            import time  # Add time module
            
            # Set matplotlib backend
            matplotlib.use('Agg')
            
            exec_globals.update({
                'pd': pd, 'pandas': pd,
                'np': np, 'numpy': np,
                'xr': xr, 'xarray': xr,
                'plt': plt, 'matplotlib': matplotlib,
                'datetime': datetime, 'timedelta': timedelta,
                'io': io,
                'time': time,  # Add time module
                'logging': logging  # Add logging module
            })
            
            logging.info("Libraries loaded successfully")
            
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