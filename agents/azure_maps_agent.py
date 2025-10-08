import json
import logging
from typing import Dict, List, Any, Optional
from .azure_maps_generator import AzureMapsGenerator

class AzureMapsAgent:
    """Agent for handling Azure Maps requests using direct data processing and generating transparent PNG overlays."""
    
    def __init__(self, subscription_key: str):
        self.subscription_key = subscription_key
        self.map_generator = AzureMapsGenerator(subscription_key)
        
    def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a map request and return both point data AND transparent PNG overlay for Azure Maps."""
        try:
            user_query = request.get('user_query', '')
            request_type = request.get('type', 'display')
            
            logging.info(f"Processing Azure Maps request with PNG overlay: {request_type} for query: {user_query}")
            
            # Extract parameters from the user query
            weather_params = self._extract_weather_parameters(user_query)
            
            if not weather_params:
                return {
                    'error': 'Could not determine weather parameters from query',
                    'suggestion': 'Please specify location, date, and variable (e.g., "show temperature in Florida on azure maps")'
                }
            
            # Fetch the weather data
            weather_data = self._fetch_weather_data_directly(weather_params)
            
            if 'error' in weather_data:
                return weather_data
            
            # NEW: Generate matplotlib PNG overlay
            overlay_result = self._generate_matplotlib_overlay(weather_data, weather_params)
            
            if 'error' in overlay_result:
                return overlay_result
            
            # Convert weather data to Azure Maps format
            map_data = self._convert_to_azure_maps_format(weather_data)
            
            return {
                'status': 'success',
                'map_config': map_data,
                'overlay_url': overlay_result['overlay_url'],  # NEW: PNG overlay URL
                'weather_data': weather_data,
                'data_type': 'azure_maps_interactive',
                'content': f"Interactive Azure Maps with transparent overlay ready. Overlay: {overlay_result['overlay_url']}"
            }
                
        except Exception as e:
            logging.error(f"Azure Maps request processing failed: {e}")
            return {'error': f'Error processing request: {str(e)}'}
    
    def _generate_matplotlib_overlay(self, weather_data: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate properly georeferenced transparent PNG overlay for Azure Maps with visible temperature colors."""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.colors import LinearSegmentedColormap
            import numpy as np
            import io
            from datetime import datetime
            from .weather_tool import save_plot_to_blob_simple, get_account_key
            
            logging.info("🎨 Generating VISIBLE temperature overlay for Azure Maps")
            
            # Extract data for overlay
            data_values = np.array(weather_data['data_values'])
            lons = np.array(weather_data['longitude'])
            lats = np.array(weather_data['latitude'])
            variable = weather_data['variable']
            unit = weather_data['unit']
            
            logging.info(f"📊 Data shape: {data_values.shape}")
            logging.info(f"📊 Data type: {data_values.dtype}")
            
            # CRITICAL FIX: Check for and handle NaN values
            nan_count = np.count_nonzero(np.isnan(data_values))
            total_count = data_values.size
            logging.info(f"🔍 NaN values: {nan_count}/{total_count} ({100*nan_count/total_count:.1f}%)")
            
            if nan_count == total_count:
                logging.error("❌ ALL DATA VALUES ARE NaN! Cannot create meaningful overlay")
                return {'error': 'All temperature data values are NaN - no valid data to visualize'}
            
            if nan_count > 0:
                logging.warning(f"⚠️ Found {nan_count} NaN values, will mask them in the visualization")
            
            # FIXED: Calculate temperature range from valid (non-NaN) values only
            valid_mask = ~np.isnan(data_values)
            if np.any(valid_mask):
                valid_data = data_values[valid_mask]
                temp_min = float(valid_data.min())
                temp_max = float(valid_data.max())
                logging.info(f"📊 Valid temperature range: {temp_min:.2f} to {temp_max:.2f} {unit}")
            else:
                logging.error("❌ No valid (non-NaN) temperature data found")
                return {'error': 'No valid temperature data available for visualization'}
            
            # CRITICAL: Calculate EXACT geographic bounds for Azure Maps
            region_bounds = {
                'west': float(lons.min()),
                'east': float(lons.max()),
                'south': float(lats.min()),
                'north': float(lats.max())
            }
            
            logging.info(f"📍 Geographic bounds: W={region_bounds['west']:.6f}, E={region_bounds['east']:.6f}, S={region_bounds['south']:.6f}, N={region_bounds['north']:.6f}")
            
            # CRITICAL: Create figure that matches EXACT geographic extent
            # Calculate aspect ratio based on geographic bounds (accounting for latitude projection)
            lat_center = (region_bounds['south'] + region_bounds['north']) / 2
            aspect_ratio = np.cos(np.radians(lat_center)) * (region_bounds['east'] - region_bounds['west']) / (region_bounds['north'] - region_bounds['south'])
            
            # Set figure size to maintain geographic aspect ratio
            fig_width = 12
            fig_height = fig_width / aspect_ratio
            
            # CRITICAL: Create figure with NO padding, NO margins for exact overlay
            fig = plt.figure(figsize=(fig_width, fig_height), frameon=False, dpi=200)
            fig.patch.set_alpha(0)  # Transparent background
            
            # CRITICAL: Create axes that fill entire figure with EXACT geographic bounds
            ax = fig.add_axes([0, 0, 1, 1])  # Full figure coverage
            ax.set_facecolor('none')  # Transparent axes
            
            # CRITICAL: Set EXACT coordinate limits to match data bounds
            ax.set_xlim(region_bounds['west'], region_bounds['east'])
            ax.set_ylim(region_bounds['south'], region_bounds['north'])
            
            # CRITICAL: Turn off ALL axes elements for clean overlay
            ax.axis('off')
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            
            # FIXED: Create proper temperature colormap with better colors and transparency
            if variable == 'Tair':
                # ENHANCED: Better temperature colors with higher contrast
                colors = ['#000080', '#0000FF', '#4169E1', '#00BFFF', '#00FFFF', '#90EE90', '#FFFF00', '#FFA500', '#FF4500', '#FF0000', '#8B0000']
                cmap = LinearSegmentedColormap.from_list('temperature_overlay', colors, N=256)
                
                # FIXED: Use valid data range instead of raw data
                vmin = temp_min
                vmax = temp_max
                
                # Add small buffer if range is too small
                if abs(vmax - vmin) < 1.0:
                    center = (vmin + vmax) / 2
                    vmin = center - 2.0
                    vmax = center + 2.0
                
                logging.info(f"🌡️ Temperature colormap range: {vmin:.2f} to {vmax:.2f} {unit}")
                
            elif variable == 'Rainf':
                # ENHANCED: Better precipitation colors
                colors = ['#FFFFFF00', '#E6F3FF', '#CCE7FF', '#80CCFF', '#4DA6FF', '#1A80FF', '#0066CC', '#004C99', '#003366']
                cmap = LinearSegmentedColormap.from_list('precipitation_overlay', colors, N=256)
                vmin = 0.1  # Start slightly above 0 for visibility
                vmax = temp_max  # Use the valid max
                
            elif variable == 'SPI3':
                # ENHANCED: Better drought colors
                colors = ['#8B0000', '#FF0000', '#FF4500', '#FFA500', '#FFFF00', '#FFFFFF80', '#87CEEB', '#4169E1', '#0000FF']
                cmap = LinearSegmentedColormap.from_list('drought_overlay', colors, N=256)
                vmin, vmax = -2.5, 2.5
                
            else:
                # Default colormap
                cmap = plt.cm.viridis
                vmin = temp_min
                vmax = temp_max
            
            # CRITICAL: Plot data with EXACT geographic coordinates and HIGHER OPACITY
            if data_values.ndim == 2:
                # Create meshgrid with EXACT coordinates
                lon_grid, lat_grid = np.meshgrid(lons, lats)
                
                logging.info(f"📐 Grid shapes: lon_grid {lon_grid.shape}, lat_grid {lat_grid.shape}, data {data_values.shape}")
                
                # FIXED: Create masked array to handle NaN values properly
                masked_data = np.ma.masked_invalid(data_values)
                
                # FIXED: Use pcolormesh with masked data and HIGHER alpha for visibility
                contour_filled = ax.pcolormesh(lon_grid, lat_grid, masked_data, 
                                             cmap=cmap, alpha=0.9,  # INCREASED alpha from 0.8 to 0.9
                                             vmin=vmin, vmax=vmax, 
                                             shading='auto')
                
                logging.info("✅ Used 2D pcolormesh with masked array for temperature overlay")
                
            else:
                # For 1D data, interpolate to regular grid
                from scipy.interpolate import griddata
                
                logging.info("🔄 Using 1D data interpolation")
                
                # Create high-resolution grid within EXACT bounds
                grid_lons = np.linspace(region_bounds['west'], region_bounds['east'], 200)
                grid_lats = np.linspace(region_bounds['south'], region_bounds['north'], 150)
                grid_X, grid_Y = np.meshgrid(grid_lons, grid_lats)
                
                # Flatten coordinates and values
                points = np.column_stack((lons.flatten(), lats.flatten()))
                values = data_values.flatten()
                
                # FIXED: Remove NaN values BEFORE interpolation
                valid_mask = ~np.isnan(values)
                points = points[valid_mask]
                values = values[valid_mask]
                
                logging.info(f"📊 Valid data points for interpolation: {len(values)}")
                
                if len(values) > 10:  # Need at least 10 points for meaningful interpolation
                    # Interpolate to regular grid
                    grid_data = griddata(points, values, (grid_X, grid_Y), method='cubic', fill_value=np.nan)
                    
                    # Create masked array for plotting
                    masked_grid_data = np.ma.masked_invalid(grid_data)
                    
                    # FIXED: Plot interpolated data with masked array and HIGHER alpha
                    contour_filled = ax.pcolormesh(grid_X, grid_Y, masked_grid_data, 
                                                 cmap=cmap, alpha=0.9,  # INCREASED alpha
                                                 vmin=vmin, vmax=vmax, 
                                                 shading='auto')
                    
                    logging.info("✅ Used interpolated pcolormesh with masked array for temperature overlay")
                else:
                    logging.error(f"❌ Only {len(values)} valid data points - insufficient for interpolation")
                    return {'error': f'Insufficient valid data points ({len(values)}) for temperature overlay'}
            
            # CRITICAL: NO colorbar, NO title, NO labels - pure data overlay only
            
            # ENHANCED: Save with better settings for visibility
            timestamp = int(datetime.now().timestamp())
            filename = f'azure_maps_temperature_overlay_{variable}_{params["region"]}_{timestamp}.png'
            
            # CRITICAL: Save with exact bounds information for frontend
            account_key = get_account_key()
            overlay_url = save_plot_to_blob_simple(fig, filename, account_key)
            
            plt.close(fig)
            
            logging.info(f"✅ Generated visible temperature overlay: {overlay_url}")
            logging.info(f"📍 Color range: {vmin:.2f} to {vmax:.2f} {unit}")
            logging.info(f"📍 Bounds for frontend: {region_bounds}")
            
            return {
                'overlay_url': overlay_url,
                'bounds': region_bounds,
                'variable': variable,
                'unit': unit,
                'color_range': {'min': vmin, 'max': vmax},
                'geographic_info': {
                    'coordinate_system': 'WGS84',
                    'projection': 'Geographic (lat/lon)',
                    'bounds_format': 'EPSG:4326',
                    'aspect_ratio': aspect_ratio
                },
                'data_quality': {
                    'total_points': total_count,
                    'valid_points': total_count - nan_count,
                    'nan_percentage': 100 * nan_count / total_count
                }
            }
            
        except Exception as e:
            logging.error(f"❌ Temperature overlay generation failed: {e}")
            import traceback
            logging.error(f"❌ Full traceback: {traceback.format_exc()}")
            return {'error': f'Failed to generate overlay: {str(e)}'}

    def _extract_weather_parameters(self, user_query: str) -> Optional[Dict[str, Any]]:
        """Extract weather analysis parameters from user query."""
        query_lower = user_query.lower()
        
        params = {
            'variable': 'Tair',  # Default to temperature
            'year': 2023,  # Default
            'month': 5,    # Default to May
            'day': 12,     # Default
            'region': 'florida',
            'lat_min': 24.5,
            'lat_max': 31.0,
            'lon_min': -87.6,
            'lon_max': -80.0
        }
        
        # Extract variable
        from .weather_tool import VARIABLE_MAPPING
        for common_name, nldas_name in VARIABLE_MAPPING.items():
            if common_name in query_lower:
                params['variable'] = nldas_name
                break
        
        # Extract region
        region_coords = {
            'florida': {'lat_min': 24.5, 'lat_max': 31.0, 'lon_min': -87.6, 'lon_max': -80.0},
            'maryland': {'lat_min': 37.9, 'lat_max': 39.7, 'lon_min': -79.5, 'lon_max': -75.0},
            'california': {'lat_min': 32.0, 'lat_max': 42.0, 'lon_min': -125.0, 'lon_max': -114.0},
            'alaska': {'lat_min': 58.0, 'lat_max': 72.0, 'lon_min': -180.0, 'lon_max': -120.0}
        }
        
        for region, coords in region_coords.items():
            if region in query_lower:
                params['region'] = region
                params.update(coords)
                break
        
        # Extract date
        import re
        
        # Look for years
        year_matches = re.findall(r'(20\d{2})', user_query)
        if year_matches:
            params['year'] = int(year_matches[0])
        
        # Look for months
        month_names = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        for month_name, month_num in month_names.items():
            if month_name in query_lower:
                params['month'] = month_num
                break
        
        # Look for days
        day_matches = re.findall(r'\b(\d{1,2})\b', user_query)
        for day_str in day_matches:
            day = int(day_str)
            if 1 <= day <= 31:
                params['day'] = day
                break
        
        return params
    
    def _fetch_weather_data_directly(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch weather data directly using weather_tool functions."""
        try:
            from .weather_tool import (
                get_account_key, 
                load_specific_date_kerchunk, 
                ACCOUNT_NAME
            )
            import builtins
            
            account_key = get_account_key()
            
            # Load NLDAS data
            ds, debug_info = load_specific_date_kerchunk(
                ACCOUNT_NAME, account_key, params['year'], params['month'], params['day']
            )
            
            # Extract data for the region
            data = ds[params['variable']].sel(
                lat=builtins.slice(params['lat_min'], params['lat_max']),
                lon=builtins.slice(params['lon_min'], params['lon_max'])
            )
            
            # Process based on variable type
            if params['variable'] == 'Rainf':
                # Sum precipitation over time
                processed_data = data.sum(dim='time')
                unit = 'mm'
            elif params['variable'] == 'Tair':
                # Average temperature and convert to Celsius
                processed_data = data.mean(dim='time') - 273.15
                unit = '°C'
            else:
                # Average for other variables
                processed_data = data.mean(dim='time')
                unit = ds[params['variable']].attrs.get('units', 'unknown')
            
            # Calculate center coordinates
            center_lon = float((processed_data.lon.min() + processed_data.lon.max()) / 2)
            center_lat = float((processed_data.lat.min() + processed_data.lat.max()) / 2)
            
            # Convert to format needed for frontend
            weather_data = {
                'data_values': processed_data.values.tolist(),
                'longitude': processed_data.lon.values.tolist(),
                'latitude': processed_data.lat.values.tolist(),
                'variable': params['variable'],
                'unit': unit,
                'date': f"{params['year']}-{params['month']:02d}-{params['day']:02d}",
                'region': params['region'],
                'center': [center_lon, center_lat]
            }
            
            ds.close()
            return weather_data
            
        except Exception as e:
            logging.error(f"Weather data fetch failed: {e}")
            return {'error': f'Failed to fetch weather data: {str(e)}'}
    
    def _convert_to_azure_maps_format(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert weather data to Azure Maps configuration format with overlay support."""
        
        # Use the center from weather data
        center = weather_data['center']
        
        # Create reduced set of data points for interactivity (not visualization)
        data_points = []
        data_values = weather_data['data_values']
        lons = weather_data['longitude']
        lats = weather_data['latitude']
        variable = weather_data.get('variable', 'Unknown')
        unit = weather_data.get('unit', '')
        
        # Sample points for hover interactivity (every 5th point to reduce load)
        if isinstance(data_values[0], list):
            for i in range(0, len(lats), 5):  # Sample every 5th row
                for j in range(0, len(lons), 5):  # Sample every 5th column
                    if i < len(data_values) and j < len(data_values[i]):
                        value = data_values[i][j]
                        if value is not None and not (isinstance(value, float) and value != value):  # Not NaN
                            data_points.append({
                                'latitude': lats[i],
                                'longitude': lons[j],
                                'value': float(value),
                                'title': f"{variable}: {value:.2f} {unit}"
                            })
        
        # Determine color scheme based on variable
        if variable == 'SPI3':
            color_scheme = 'drought'
            value_range = [-2.5, 2.5]
        elif variable == 'Tair':
            color_scheme = 'temperature'
            value_range = [min(point['value'] for point in data_points), 
                          max(point['value'] for point in data_points)]
        elif variable == 'Rainf':
            color_scheme = 'precipitation'
            value_range = [0, max(point['value'] for point in data_points)]
        else:
            color_scheme = 'default'
            value_range = [min(point['value'] for point in data_points), 
                          max(point['value'] for point in data_points)]
        
        return {
            'subscription_key': self.subscription_key,
            'center': center,
            'zoom': 7,
            'style': 'satellite',
            'data_points': data_points,  # Reduced set for interactivity
            'color_scheme': color_scheme,
            'value_range': value_range,
            'legend': {
                'title': f"{variable} ({unit})",
                'date': weather_data.get('date', 'Unknown'),
                'region': weather_data.get('region', 'Unknown')
            },
            'overlay_mode': True  # NEW: Indicates this uses PNG overlay
        }

# Helper function for the main function_app.py  
def handle_azure_maps_chat(user_query: str, project_client) -> Dict[str, Any]:
    """Helper function to handle Azure Maps requests from function_app.py"""
    try:
        import os
        azure_maps_key = os.environ.get('AZURE_MAPS_SUBSCRIPTION_KEY', 'your-key-here')
        
        agent = AzureMapsAgent(azure_maps_key)
        
        # Create a simple request structure
        map_request = {
            'user_query': user_query,
            'type': 'display'
        }
        
        response = agent.process_request(map_request)
        
        return {
            'content': 'Azure Maps data prepared for interactive rendering',
            'data': response,
            'type': 'azure_maps_interactive'
        }
            
    except Exception as e:
        logging.error(f"Azure Maps chat handler failed: {e}")
        return {
            'content': f'Azure Maps processing failed: {str(e)}',
            'type': 'error'
        }
