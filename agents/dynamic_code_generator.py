import json
import logging
import traceback
import builtins
import time

def execute_custom_code(args: dict):
    """
    Execute custom Python code with proper NLDAS-3 environment setup
    """
    try:
        user_request = args.get("user_request", "Unknown request")
        python_code = args.get("python_code", "")
        
        logging.info(f"=== EXECUTE_CUSTOM_CODE CALLED ===")
        logging.info(f"User request: {user_request}")
        logging.info(f"Python code provided: {bool(python_code)}")
        logging.info(f"Code length: {len(python_code) if python_code else 0}")
        
        if not python_code:
            return {
                "status": "error",
                "error": "No Python code provided",
                "user_request": user_request
            }
        
        # Log first few lines of code for debugging
        code_lines = python_code.split('\n')[:5]
        logging.info(f"Code preview (first 5 lines): {code_lines}")
        
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
                    time.sleep(1)
            
            # Define the process_daily_data function that the agent needs
            def process_daily_data(data, variable_name):
                """
                Apply appropriate aggregation based on variable type
                """
                # Variables that should be summed (accumulated)
                accumulation_vars = ['Rainf', 'LWdown', 'SWdown']
                
                if variable_name in accumulation_vars:
                    # Sum for precipitation and radiation (daily totals)
                    return data.sum(dim='time')
                else:
                    # Mean for temperature, humidity, pressure, wind (daily averages)
                    return data.mean(dim='time')
            
            # Add all weather functions to execution environment
            exec_globals.update({
                'load_specific_date_kerchunk': load_specific_date_kerchunk,
                'save_plot_to_blob_simple': save_plot_to_blob_simple,
                'get_account_key': get_account_key,
                'find_available_kerchunk_files': find_available_kerchunk_files,
                'ACCOUNT_NAME': ACCOUNT_NAME,
                'account_key': account_key,  # Real account key
                'VARIABLE_MAPPING': VARIABLE_MAPPING,
                'process_daily_data': process_daily_data,  # Add the helper function
                'user_request': user_request  # Make user_request available for dynamic parsing
            })
            
            logging.info(f"Weather functions loaded. ACCOUNT_NAME: {ACCOUNT_NAME}")
            
        except Exception as e:
            logging.error(f"Failed to import weather functions: {e}")
            return {
                "status": "error",
                "error": f"Failed to load weather functions: {str(e)}",
                "user_request": user_request
            }
        
        # Import data science libraries with proper logging scope
        try:
            import pandas as pd
            import numpy as np
            import xarray as xr
            import matplotlib
            import matplotlib.pyplot as plt
            import datetime as datetime_module  # Import the module, not just the class
            from datetime import datetime, timedelta
            import io
            import re  # Add regex for date parsing
            # Note: logging is already imported at module level
            
            # Import Cartopy for geographic features with detailed logging
            try:
                import cartopy
                import cartopy.crs as ccrs
                import cartopy.feature as cfeature
                cartopy_available = True
                cartopy_version = cartopy.__version__
                logging.info(f"✅ Cartopy {cartopy_version} successfully imported")
                
                # Try to import shapereader for state labels
                try:
                    import cartopy.io.shapereader as shpreader
                    shapereader_available = True
                    logging.info("✅ Cartopy shapereader available for state labels")
                except ImportError:
                    shapereader_available = False
                    logging.warning("⚠️ Cartopy shapereader not available - no state labels")
                
                # Test basic Cartopy functionality
                try:
                    test_crs = ccrs.PlateCarree()
                    test_feature = cfeature.COASTLINE
                    logging.info("✅ Cartopy basic functionality test passed")
                except Exception as cartopy_test_error:
                    logging.warning(f"⚠️ Cartopy test failed: {cartopy_test_error}")
                    cartopy_available = False
                    
            except ImportError as cartopy_import_error:
                cartopy_available = False
                shapereader_available = False
                logging.warning(f"❌ Cartopy import failed: {cartopy_import_error}")
                logging.warning("💡 To install Cartopy: pip install cartopy")
            except Exception as cartopy_error:
                cartopy_available = False
                shapereader_available = False
                logging.error(f"❌ Cartopy error: {cartopy_error}")
            
            # Import Azure Storage modules that might be needed
            try:
                from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
                azure_storage_available = True
            except ImportError:
                azure_storage_available = False
                logging.warning("Azure Storage modules not available")
            
            # Import PIL for GIF creation
            try:
                from PIL import Image
                pil_available = True
            except ImportError:
                pil_available = False
                logging.warning("PIL not available - GIF creation will be disabled")
            
            # Set matplotlib backend
            matplotlib.use('Agg')
            
            # 🎯 GLOBAL FONT SIZE CONFIGURATION - ALL TEXT AT 16PT
            plt.rcParams.update({
                'font.size': 16,          # Base font size (affects all text)
                'axes.titlesize': 18,     # Title font size (slightly larger)
                'axes.labelsize': 16,     # Axis label font size
                'xtick.labelsize': 16,    # X-axis tick label size
                'ytick.labelsize': 16,    # Y-axis tick label size
                'legend.fontsize': 16,    # Legend font size
                'figure.titlesize': 18,   # Figure title size
                'axes.titlepad': 20,      # Add padding for titles
                'axes.labelpad': 10,      # Add padding for labels
                'legend.frameon': True,   # Show legend frame
                'legend.fancybox': True,  # Rounded legend corners
                'legend.shadow': False,   # No shadow
                'legend.framealpha': 0.9, # Legend background transparency
                'grid.alpha': 0.3,        # Grid transparency
                'lines.linewidth': 2.0,   # Default line width
                'lines.markersize': 8,    # Default marker size
                'savefig.dpi': 150,       # High DPI for crisp images
                'savefig.bbox': 'tight',  # Tight bounding box
                'savefig.facecolor': 'white',  # White background
                'figure.facecolor': 'white',   # White figure background
                'axes.facecolor': 'white',     # White axes background
            })
            
            logging.info("✅ Global matplotlib font configuration set to 16pt minimum")
            
            # CRITICAL: Block animation module to prevent errors
            # Enable animation support for static frame generation
            try:
                import matplotlib.animation as animation_module
                animation_available = True
                logging.info("✅ Animation module enabled for static frame generation")
                
                # Helper function for creating GIFs from static frames
                def create_gif_from_frames(frame_images, output_path=None, duration=1000):
                    """
                    Create GIF from PIL Image frames
                    """
                    if not frame_images or not PIL_AVAILABLE:
                        return None
                        
                    try:
                        if output_path:
                            frame_images[0].save(output_path, save_all=True, 
                                            append_images=frame_images[1:], 
                                            duration=duration, loop=0, format='GIF')
                            return output_path
                        else:
                            # Return as BytesIO buffer
                            gif_buffer = io.BytesIO()
                            frame_images[0].save(gif_buffer, save_all=True, 
                                            append_images=frame_images[1:], 
                                            duration=duration, loop=0, format='GIF')
                            return gif_buffer
                    except Exception as e:
                        logging.error(f"GIF creation failed: {e}")
                        return None
                
            except ImportError:
                animation_available = False
                animation_module = None
                def create_gif_from_frames(*args, **kwargs):
                    return None
                logging.warning("Animation module not available")   
            exec_globals.update({
                'pd': pd, 'pandas': pd,
                'np': np, 'numpy': np,
                'xr': xr, 'xarray': xr,
                'plt': plt, 'matplotlib': matplotlib,
                'datetime': datetime_module,  # Provide the module
                'timedelta': timedelta,
                'io': io,
                'logging': logging,  # Pass the module-level logging
                'Image': Image if pil_available else None,
                'PIL_AVAILABLE': pil_available,
                're': re,  # Add regex module
                # Cartopy modules
                'ccrs': ccrs if cartopy_available else None,
                'cfeature': cfeature if cartopy_available else None,
                'CARTOPY_AVAILABLE': cartopy_available,
                'shpreader': shpreader if cartopy_available and shapereader_available else None,
                'SHAPEREADER_AVAILABLE': shapereader_available if cartopy_available else False,
                # Azure Storage modules
                'BlobServiceClient': BlobServiceClient if azure_storage_available else None,
                'generate_blob_sas': generate_blob_sas if azure_storage_available else None,
                'BlobSasPermissions': BlobSasPermissions if azure_storage_available else None,
                'AZURE_STORAGE_AVAILABLE': azure_storage_available
            })
            
            logging.info(f"Libraries loaded successfully. PIL: {pil_available}, Azure Storage: {azure_storage_available}, Cartopy: {cartopy_available}, ShapeReader: {shapereader_available if cartopy_available else False}")
            
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
            
            # Log the actual code being executed to debug import issues
            logging.info("=== PYTHON CODE BEING EXECUTED ===")
            logging.info(python_code)
            logging.info("=== END OF PYTHON CODE ===")
            
            # CRITICAL: Validate code before execution to prevent bad imports
            forbidden_patterns = [
                'import some_module',
                'from some_module',
                'import unknown',
                'from unknown',
                'import matplotlib.animation',
                'from matplotlib.animation',
                # REMOVED: 'import PIL' and 'from PIL import Image' - these should be allowed since Image is pre-loaded
                'from PIL import',        # Block other PIL imports but allow 'from PIL import Image'
                'import azure.storage.blob',
                'from azure.storage.blob import BlobServiceClient',
                'from azure.storage.blob import generate_blob_sas',
                'from azure.storage.blob import BlobSasPermissions',
                'from azure.storage.blob import',
                'from azure.storage.blob',
                'azure.storage.blob import BlobServiceClient',
                'azure.storage.blob import generate_blob_sas',
                'azure.storage.blob import BlobSasPermissions',
                'BlobServiceClient, generate_blob_sas',
                'generate_blob_sas, BlobSasPermissions'
            ]
            
            # Check for forbidden patterns with better error handling
            try:
                python_code_lower = python_code.lower()
                for pattern in forbidden_patterns:
                    if pattern.lower() in python_code_lower:
                        # UPDATED: Allow specific PIL imports
                        if pattern == 'from PIL import' and 'from PIL import Image' in python_code:
                            continue  # Allow this specific case
                        
                        # Provide specific guidance for different error types
                        if 'animation' in pattern:
                            error_msg = (f"Animation creation error: '{pattern}' is forbidden. "
                                       f"matplotlib.animation is blocked - create individual frames and combine with PIL using pre-loaded modules.")
                        elif 'azure.storage.blob' in pattern or 'blobserviceclient' in pattern.lower():
                            error_msg = (f"Azure Storage import error: '{pattern}' is STRICTLY FORBIDDEN. "
                                       f"NEVER import Azure modules. Use pre-loaded variables: BlobServiceClient, generate_blob_sas, BlobSasPermissions. "
                                       f"Check AZURE_STORAGE_AVAILABLE first. "
                                       f"Example: if AZURE_STORAGE_AVAILABLE: blob_client = BlobServiceClient(...)")
                        else:
                            error_msg = f"Forbidden import pattern detected: '{pattern}'. Use pre-loaded modules instead."
                        
                        logging.error(f"Code validation failed: {error_msg}")
                        
                        # Also log the actual problematic line
                        for line_num, line in enumerate(python_code.split('\n'), 1):
                            if pattern.lower() in line.lower():
                                logging.error(f"Problematic line {line_num}: {line}")
                        
                        return {
                            "status": "error",
                            "error": error_msg,
                            "python_code": python_code[:500],
                            "user_request": user_request,
                            "validation_failed": True,
                            "suggestion": "Remove ALL import statements. Use pre-loaded variables directly: BlobServiceClient, generate_blob_sas, BlobSasPermissions"
                        }
                
                # Additional validation: check for suspicious import lines (WARNING ONLY)
                import_lines = [line.strip() for line in python_code.split('\n') if line.strip().startswith(('import ', 'from '))]
                allowed_imports = ['import builtins', 'import re', 'from datetime import']
                
                for import_line in import_lines:
                    if not any(allowed in import_line for allowed in allowed_imports):
                        # Only log as warning, don't block execution
                        if not any(blocked in import_line.lower() for blocked in ['matplotlib.animation', 'from pil import', 'azure.storage.blob']):
                            logging.info(f"INFO: Pre-loaded import detected: {import_line}")
                        else:
                            logging.warning(f"Suspicious import detected: {import_line}")
                
            except Exception as validation_error:
                logging.error(f"Code validation error: {validation_error}")
                # Continue with execution if validation fails
            
            exec(python_code, exec_globals, exec_locals)
            
            # Get result
            result = exec_locals.get('result', 'No result variable found')
            
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