# tiles_endpoint.py - COMPLETE VERSION with Wind_Speed support

from fastapi import APIRouter, Response, HTTPException
import mercantile
import numpy as np
from PIL import Image
import io
import logging
from scipy.ndimage import zoom
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server use
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from matplotlib.colors import Normalize, LinearSegmentedColormap

router = APIRouter()

from agents.weather_tool import (
    load_specific_date_kerchunk,
    load_specific_month_spi_kerchunk,
    get_account_key,
    ACCOUNT_NAME
)

# ✅ CRITICAL: Global color scale definitions (same for ALL tiles)
VARIABLE_COLOR_SCALES = {
    'Tair': {
        'vmin': -40.0,  # Global minimum temperature (°C)
        'vmax': 50.0,   # Global maximum temperature (°C)
        'cmap': 'RdYlBu_r'
    },
    'Rainf': {
        'vmin': 0.0,    # Minimum precipitation (mm)
        'vmax': 100.0,  # Maximum precipitation (mm)
        'cmap': 'Blues'
    },
    'SPI3': {
        'vmin': -2.5,   # SPI minimum (extreme drought)
        'vmax': 2.5,    # SPI maximum (extreme wet)
        'cmap': 'RdBu'
    },
    'Qair': {
        'vmin': 0.0,
        'vmax': 0.03,
        'cmap': 'BrBG'
    },
    'PSurf': {
        'vmin': 80000,
        'vmax': 105000,
        'cmap': 'viridis'
    },
    'Wind_Speed': {
        'vmin': 0.0,
        'vmax': 20.0,
        'cmap': 'viridis'
    }
}

def get_color_scale(variable: str):
    """Get consistent color scale for a variable"""
    if variable in VARIABLE_COLOR_SCALES:
        return VARIABLE_COLOR_SCALES[variable]
    else:
        # Default fallback
        logging.warning(f"⚠️ No color scale defined for {variable}, using default")
        return {'vmin': 0, 'vmax': 100, 'cmap': 'viridis'}

@router.get("/tiles/{variable}/{date}/{z}/{x}/{y}.png")
@router.head("/tiles/{variable}/{date}/{z}/{x}/{y}.png")
async def get_weather_tile(
    variable: str,
    date: str,
    z: int,
    x: int,
    y: int,
    vmin: float = None,  # Accept region-specific vmin
    vmax: float = None,  # Accept region-specific vmax
    cmap: str = None     # ✅ FIXED: Accept colormap parameter
):
    """
    Generate a 256x256 weather tile with REGION-SPECIFIC color scale
    ✅ ALWAYS returns exactly 256x256 pixels for Azure Maps compatibility
    ✅ Supports Wind_Speed calculation from Wind_E and Wind_N components
    """
    try:
        logging.info(f"🗺️ Tile request: {variable}/{date}/{z}/{x}/{y} (cmap={cmap})")
        
        # ✅ Get GLOBAL color scale for this variable (same for all tiles!)
        color_config = get_color_scale(variable)
        
        # ✅ FIXED: Use cmap parameter if provided, otherwise fall back to default
        cmap_name = cmap if cmap else color_config['cmap']
        
        # STEP 1: Get tile bounds
        tile = mercantile.Tile(x, y, z)
        bounds = mercantile.bounds(tile)
        
        logging.info(f"📍 Tile bounds: N={bounds.north:.4f}, S={bounds.south:.4f}, W={bounds.west:.4f}, E={bounds.east:.4f}")
        
        # STEP 2: Load data
        date_parts = date.split('-')
        year = int(date_parts[0])
        month = int(date_parts[1])
        account_key = get_account_key()
        
        if variable == 'SPI3':
            ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, month)
            lat_name = 'latitude'
            lon_name = 'longitude'
        else:
            day = int(date_parts[2])
            ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
            lat_name = 'lat'
            lon_name = 'lon'
        
        # STEP 3: Check coordinate order
        lat_coords = ds[lat_name].values
        lon_coords = ds[lon_name].values
        lat_descending = lat_coords[0] > lat_coords[-1]
        
        logging.info(f"📊 Coordinates: lat={lat_coords.min():.2f} to {lat_coords.max():.2f} ({'DESC' if lat_descending else 'ASC'})")
        
        # STEP 4: Prepare slices
        if lat_descending:
            lat_slice = slice(bounds.north, bounds.south)
        else:
            lat_slice = slice(bounds.south, bounds.north)
        
        lon_slice = slice(bounds.west, bounds.east)
        
        # STEP 4.5: ✅ CRITICAL: Handle Wind_Speed specially
        if variable == 'Wind_Speed' or variable == 'wind_speed':
            logging.info("🌬️ Calculating Wind_Speed from Wind_E and Wind_N components")
            
            try:
                # Load both wind components with error handling
                wind_e = ds['Wind_E'].sel(
                    **{lat_name: lat_slice, lon_name: lon_slice}
                )
                wind_n = ds['Wind_N'].sel(
                    **{lat_name: lat_slice, lon_name: lon_slice}
                )
                
                logging.info(f"📊 Wind_E shape: {wind_e.shape}, Wind_N shape: {wind_n.shape}")
                
                # ✅ CRITICAL: Check for empty data BEFORE processing
                if wind_e.size == 0 or wind_n.size == 0:
                    logging.warning(f"⚠️ Empty wind component data for tile {z}/{x}/{y}")
                    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG', optimize=True)
                    buffer.seek(0)
                    ds.close()
                    return Response(content=buffer.getvalue(), media_type='image/png')
                
                # Apply temporal averaging FIRST (before calculating magnitude)
                if 'time' in wind_e.dims:
                    wind_e = wind_e.mean(dim='time')
                    logging.info("✅ Averaged Wind_E over time")
                if 'time' in wind_n.dims:
                    wind_n = wind_n.mean(dim='time')
                    logging.info("✅ Averaged Wind_N over time")
                
                # ✅ CRITICAL: Check again after temporal averaging
                if wind_e.size == 0 or wind_n.size == 0:
                    logging.warning(f"⚠️ Empty wind data after time averaging for tile {z}/{x}/{y}")
                    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG', optimize=True)
                    buffer.seek(0)
                    ds.close()
                    return Response(content=buffer.getvalue(), media_type='image/png')
                
                # Calculate wind speed magnitude: sqrt(Wind_E² + Wind_N²)
                data = np.sqrt(wind_e**2 + wind_n**2)
                
                # ✅ CRITICAL: Validate result before proceeding
                if data.size == 0:
                    logging.warning(f"⚠️ Zero-size wind speed array for tile {z}/{x}/{y}")
                    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG', optimize=True)
                    buffer.seek(0)
                    ds.close()
                    return Response(content=buffer.getvalue(), media_type='image/png')
                
                logging.info(f"✅ Calculated wind speed: min={float(data.min()):.2f}, max={float(data.max()):.2f} m/s")
                
            except Exception as wind_error:
                logging.error(f"❌ Wind speed calculation failed for tile {z}/{x}/{y}: {wind_error}")
                img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
                buffer = io.BytesIO()
                img.save(buffer, format='PNG', optimize=True)
                buffer.seek(0)
                ds.close()
                return Response(content=buffer.getvalue(), media_type='image/png')

        else:
            # Normal variable loading
            data = ds[variable].sel(
                **{lat_name: lat_slice, lon_name: lon_slice}
            )
            
            logging.info(f"📊 Sliced data shape: {data.shape}")
            
            # STEP 5: Process temporal dimension
            if variable != 'SPI3':
                if variable == 'Tair':
                    data = data.mean(dim='time') - 273.15  # Convert to Celsius
                elif variable == 'Rainf':
                    data = data.sum(dim='time')
                else:
                    if 'time' in data.dims:
                        data = data.mean(dim='time')
        
        # STEP 6: Extract values
        if hasattr(data, 'squeeze'):
            data = data.squeeze()
        
        values = data.values
        
        logging.info(f"📊 Values shape: {values.shape}")
        
        # STEP 7: Handle empty data
        if values.size == 0:
            logging.warning(f"⚠️ Zero-size data array for tile {z}/{x}/{y}")
            img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
            buffer = io.BytesIO()
            img.save(buffer, format='PNG', optimize=True)
            buffer.seek(0)
            ds.close()
            return Response(content=buffer.getvalue(), media_type='image/png')
        
        # Log actual data range (for debugging)
        finite_values = values[np.isfinite(values)]
        if finite_values.size > 0:
            actual_min = np.min(finite_values)
            actual_max = np.max(finite_values)
            logging.info(f"📊 Tile data range: {actual_min:.2f} to {actual_max:.2f}")
        else:
            logging.warning(f"⚠️ No finite values in tile {z}/{x}/{y}")
            img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
            buffer = io.BytesIO()
            img.save(buffer, format='PNG', optimize=True)
            buffer.seek(0)
            ds.close()
            return Response(content=buffer.getvalue(), media_type='image/png')
        
        # STEP 8: Fix orientation
        if not lat_descending:
            logging.info("🔄 Flipping data (lat ascending → north at top)")
            values = np.flipud(values)
        
        # STEP 9: Resample to 256x256
        target_size = 256  # ✅ ALWAYS 256x256 for web map compatibility
        
        if values.shape != (target_size, target_size):
            zoom_y = target_size / values.shape[0]
            zoom_x = target_size / values.shape[1]
            
            logging.info(f"📏 Resampling from {values.shape} to ({target_size}, {target_size})")
            values = zoom(values, (zoom_y, zoom_x), order=1, mode='nearest')
            
            # Verify exact size after resampling
            if values.shape != (target_size, target_size):
                # Force exact size if zoom didn't get it perfect
                from skimage.transform import resize
                values = resize(values, (target_size, target_size), preserve_range=True, anti_aliasing=True)
        
        # Final verification
        assert values.shape == (target_size, target_size), f"Tile must be exactly {target_size}x{target_size}, got {values.shape}"
        
        # ✅ STEP 10: Apply REGION-SPECIFIC color scale
        valid_mask = np.isfinite(values)

        if not valid_mask.any():
            img = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
        else:
            # Use region-specific scale if provided, otherwise use variable defaults
            if vmin is not None and vmax is not None:
                # Use the region-specific scale passed from backend
                tile_vmin, tile_vmax = float(vmin), float(vmax)
                logging.info(f"🎨 Using REGION-SPECIFIC scale: [{tile_vmin:.2f}, {tile_vmax:.2f}], cmap={cmap_name}")
            else:
                # Fallback to variable-specific defaults
                tile_vmin = color_config['vmin']
                tile_vmax = color_config['vmax']
                logging.info(f"🎨 Using DEFAULT scale: [{tile_vmin:.2f}, {tile_vmax:.2f}], cmap={cmap_name}")
            
            # Normalize using region-specific scale
            if tile_vmax == tile_vmin:
                normalized = np.ones_like(values) * 0.5
            else:
                normalized = (values - tile_vmin) / (tile_vmax - tile_vmin)
                normalized = np.clip(normalized, 0, 1)
            
            # ✅ FIXED: Create RGBA image with the correct colormap
            cmap_obj = cm.get_cmap(cmap_name)
            rgba = (cmap_obj(normalized) * 255).astype(np.uint8)
            
            # Set invalid pixels to transparent
            rgba[~valid_mask, 3] = 0
            
            img = Image.fromarray(rgba, 'RGBA')
            logging.info(f"✅ Generated tile: {img.size}, region-specific colors with {cmap_name}")
        
        # ✅ Final verification before return
        assert img.size == (target_size, target_size), f"Final image must be {target_size}x{target_size}, got {img.size}"
        
        logging.info(f"✅ Generated {target_size}x{target_size} tile with region-specific colors")
        
        # STEP 11: Return PNG
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', optimize=True, compress_level=6)
        buffer.seek(0)
        
        ds.close()
        
        return Response(
            content=buffer.getvalue(),
            media_type='image/png',
            headers={
                'Cache-Control': 'public, max-age=86400',
                'Access-Control-Allow-Origin': '*',
                'X-Tile-Coords': f'{z}/{x}/{y}',
                'X-Tile-Size': f'{target_size}x{target_size}',
                'X-Color-Scale': f'{tile_vmin},{tile_vmax}' if vmin is not None else 'default',
                'X-Colormap': cmap_name  # ✅ FIXED: Include colormap in headers
            }
        )
        
    except Exception as e:
        logging.error(f"❌ Tile error {z}/{x}/{y}: {str(e)}", exc_info=True)
        
        # Return 256x256 transparent tile on error
        target_size = 256
        img = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return Response(
            content=buffer.getvalue(),
            media_type='image/png',
            headers={
                'X-Error': str(e)[:100],
                'X-Tile-Size': f'{target_size}x{target_size}'
            }
        )

@router.get("/tiles/health")
async def tiles_health():
    """Health check for tiles endpoint"""
    return {"status": "healthy", "service": "weather-tiles"}

@router.get("/tiles/colorscales")
async def get_color_scales():
    """Return the global color scales for all variables"""
    return VARIABLE_COLOR_SCALES