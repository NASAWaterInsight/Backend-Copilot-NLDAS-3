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
            
            # Set matplotlib backend
            matplotlib.use('Agg')
            
            exec_globals.update({
                'pd': pd, 'pandas': pd,
                'np': np, 'numpy': np,
                'xr': xr, 'xarray': xr,
                'plt': plt, 'matplotlib': matplotlib,
                'datetime': datetime, 'timedelta': timedelta,
                'io': io
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