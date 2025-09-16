import json
import logging
import traceback
import builtins

def execute_custom_code(args: dict):
    """
    Execute custom Python code with proper NLDAS-3 environment setup including Azure Maps
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
            from .weather_tool_new import (
                load_specific_date_kerchunk, 
                save_plot_to_blob_simple,
                get_account_key,
                find_available_kerchunk_files,
                ACCOUNT_NAME,
                VARIABLE_MAPPING,
                save_geojson_to_blob,        # ← Azure Maps function
                create_azure_map_html        # ← Azure Maps function
            )
            
            # Get actual account key
            account_key = get_account_key()
            
            # Variable labels and units for plotting
            VARIABLE_LABELS = {
                'Tair': 'Air Temperature (K)',
                'Rainf': 'Precipitation Rate (kg/m²/s)', 
                'Qair': 'Specific Humidity (kg/kg)',
                'Wind_E': 'Eastward Wind (m/s)',
                'Wind_N': 'Northward Wind (m/s)',
                'PSurf': 'Surface Pressure (Pa)',
                'LWdown': 'Longwave Radiation (W/m²)',
                'SWdown': 'Shortwave Radiation (W/m²)'
            }
            
            # Add all weather functions to execution environment
            exec_globals.update({
                'load_specific_date_kerchunk': load_specific_date_kerchunk,
                'save_plot_to_blob_simple': save_plot_to_blob_simple,
                'get_account_key': get_account_key,
                'find_available_kerchunk_files': find_available_kerchunk_files,
                'save_geojson_to_blob': save_geojson_to_blob,          # ← Azure Maps
                'create_azure_map_html': create_azure_map_html,        # ← Azure Maps
                'ACCOUNT_NAME': ACCOUNT_NAME,
                'account_key': account_key,  # Real account key
                'VARIABLE_MAPPING': VARIABLE_MAPPING,
                'VARIABLE_LABELS': VARIABLE_LABELS,  # ← For proper plot labels
            })
            
            logging.info(f"Weather functions loaded. ACCOUNT_NAME: {ACCOUNT_NAME}")
            logging.info("Azure Maps functions available: save_geojson_to_blob, create_azure_map_html")
            
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
            import os
            
            # Set matplotlib backend for Azure Functions
            matplotlib.use('Agg')
            
            exec_globals.update({
                'pd': pd, 'pandas': pd,
                'np': np, 'numpy': np,
                'xr': xr, 'xarray': xr,
                'plt': plt, 'matplotlib': matplotlib,
                'datetime': datetime, 'timedelta': timedelta,
                'io': io,
                'time': time,
                'os': os,
                'json': json,
                'logging': logging
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
            
            # Get result
            result = exec_locals.get('result', 'No result variable found')
            
            logging.info(f"Code executed successfully. Result type: {type(result)}")
            if isinstance(result, (int, float, str, dict, list)):
                logging.info(f"Result value: {result}")
            
            return {
                "status": "success",
                "result": result,
                "python_code": python_code,
                "user_request": user_request,
                "execution_environment": {
                    "weather_functions_loaded": True,
                    "azure_maps_available": True,
                    "variable_labels_available": True
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            traceback_str = traceback.format_exc()
            
            logging.error(f"Code execution failed: {error_msg}")
            logging.error(f"Full traceback: {traceback_str}")
            
            return {
                "status": "error",
                "error": f"Code execution failed: {error_msg}",
                "traceback": traceback_str[-1000:],  # Last 1000 chars of traceback
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

def get_available_functions():
    """
    Return information about available functions for debugging
    """
    return {
        "weather_functions": [
            "load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)",
            "save_plot_to_blob_simple(figure, filename, account_key)",
            "find_available_kerchunk_files(ACCOUNT_NAME, account_key)",
            "save_geojson_to_blob(data, filename, account_key)",
            "create_azure_map_html(data_url, variable_type, center_coords)"
        ],
        "data_science_libraries": [
            "pandas as pd",
            "numpy as np", 
            "xarray as xr",
            "matplotlib.pyplot as plt"
        ],
        "variables_available": [
            "ACCOUNT_NAME",
            "account_key",
            "VARIABLE_MAPPING", 
            "VARIABLE_LABELS"
        ],
        "variable_labels": {
            "Tair": "Air Temperature (K)",
            "Rainf": "Precipitation Rate (kg/m²/s)", 
            "Qair": "Specific Humidity (kg/kg)",
            "Wind_E": "Eastward Wind (m/s)",
            "Wind_N": "Northward Wind (m/s)",
            "PSurf": "Surface Pressure (Pa)",
            "LWdown": "Longwave Radiation (W/m²)",
            "SWdown": "Shortwave Radiation (W/m²)"
        }
    }

def validate_python_code(code):
    """
    Basic validation of Python code before execution
    """
    try:
        # Check for basic syntax
        compile(code, '<string>', 'exec')
        
        # Check for potentially dangerous operations
        dangerous_patterns = [
            'import subprocess', 
            'import sys',
            '__import__',
            'eval(',
            'input(',
            'raw_input(',
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern in code_lower:
                return False, f"Potentially dangerous operation detected: {pattern}"
        
        return True, "Code validation passed"
        
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"

# Test function for development
def test_execution_environment():
    """
    Test that all required functions and libraries are available
    """
    test_code = """
# Test basic imports and functions
import matplotlib.pyplot as plt
import xarray as xr
import numpy as np

# Test weather functions availability
print(f"Account name: {ACCOUNT_NAME}")
print(f"Variable mapping available: {len(VARIABLE_MAPPING)} mappings")
print(f"Variable labels available: {len(VARIABLE_LABELS)} labels")
print(f"Functions available:")
print(f"  - load_specific_date_kerchunk: {type(load_specific_date_kerchunk)}")
print(f"  - save_plot_to_blob_simple: {type(save_plot_to_blob_simple)}")
print(f"  - save_geojson_to_blob: {type(save_geojson_to_blob)}")
print(f"  - create_azure_map_html: {type(create_azure_map_html)}")

# Test variable label lookup
test_var = 'Tair'
test_label = VARIABLE_LABELS.get(test_var, test_var)
print(f"Variable {test_var} -> Label: {test_label}")

result = "Environment test successful - All functions and labels available"
"""
    
    test_args = {
        "python_code": test_code,
        "user_request": "test_environment"
    }
    
    return execute_custom_code(test_args)

if __name__ == "__main__":
    # Test the execution environment
    logging.basicConfig(level=logging.INFO)
    test_result = test_execution_environment()
    print("Test result:", json.dumps(test_result, indent=2))