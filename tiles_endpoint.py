from fastapi import APIRouter, Response, HTTPException
import mercantile
import numpy as np
from PIL import Image
import io
import logging
from scipy.ndimage import zoom

router = APIRouter()

from agents.weather_tool import (
    load_specific_date_kerchunk,
    load_specific_month_spi_kerchunk,
    get_account_key,
    ACCOUNT_NAME
)

@router.get("/tiles/{variable}/{date}/{z}/{x}/{y}.png")
async def get_weather_tile(
    variable: str,
    date: str,
    z: int,
    x: int,
    y: int
):
    """
    Generate a 256x256 weather tile for Azure Maps
    """
    try:
        logging.info(f"🗺️ Tile request: {variable}/{date}/{z}/{x}/{y}")
        
        # STEP 1: Get tile bounds (Web Mercator XYZ → WGS84)
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
        logging.info(f"📊 Coordinates: lon={lon_coords.min():.2f} to {lon_coords.max():.2f}")
        
        # STEP 4: Slice data correctly
        # xarray.sel() with slice() requires: 
        #   - For descending coords: slice(high, low)
        #   - For ascending coords: slice(low, high)
        
        if lat_descending:
            # Latitude decreases → slice(north, south)
            lat_slice = slice(bounds.north, bounds.south)
        else:
            # Latitude increases → slice(south, north)
            lat_slice = slice(bounds.south, bounds.north)
        
        lon_slice = slice(bounds.west, bounds.east)
        
        data = ds[variable].sel(
            **{lat_name: lat_slice, lon_name: lon_slice}
        )
        
        logging.info(f"📊 Sliced data shape: {data.shape}")
        
        # STEP 5: Process temporal dimension (for daily data)
        if variable != 'SPI3':
            if variable == 'Tair':
                data = data.mean(dim='time') - 273.15  # Convert to Celsius
            elif variable == 'Rainf':
                data = data.sum(dim='time')
            else:
                data = data.mean(dim='time')
        
        # STEP 6: Extract values
        if hasattr(data, 'squeeze'):
            data = data.squeeze()
        
        values = data.values
        
        logging.info(f"📊 Values shape: {values.shape}")
        logging.info(f"📊 Value range: {np.nanmin(values):.2f} to {np.nanmax(values):.2f}")
        
        # STEP 7: Handle empty tiles
        if values.size == 0 or not np.isfinite(values).any():
            logging.warning(f"⚠️ No valid data for tile {z}/{x}/{y}")
            img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
            buffer = io.BytesIO()
            img.save(buffer, format='PNG', optimize=True)
            buffer.seek(0)
            return Response(content=buffer.getvalue(), media_type='image/png')
        
        # STEP 8: CRITICAL FIX - Ensure correct orientation
        # After slicing:
        # - If lat is descending: data[0] = north, data[-1] = south ✓ (correct for image)
        # - If lat is ascending: data[0] = south, data[-1] = north ✗ (need to flip)
        
        if not lat_descending:
            # For ascending coordinates, flip to get north at top
            logging.info("🔄 Flipping data (lat ascending → north at top)")
            values = np.flipud(values)
        else:
            logging.info("✅ No flip needed (lat already north-to-south)")
        
        # STEP 9: Resample to 256x256
        if values.shape != (256, 256):
            target_height, target_width = 256, 256
            zoom_y = target_height / values.shape[0]
            zoom_x = target_width / values.shape[1]
            
            logging.info(f"📏 Resampling from {values.shape} to (256, 256) with zoom=({zoom_y:.2f}, {zoom_x:.2f})")
            
            values = zoom(values, (zoom_y, zoom_x), order=1, mode='nearest')
            
            logging.info(f"📏 Resampled shape: {values.shape}")
        
        # STEP 10: Apply colormap
        valid_mask = np.isfinite(values)
        
        if not valid_mask.any():
            img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        else:
            # Normalize values
            if variable == 'SPI3':
                # SPI: -2.5 to +2.5 scale
                vmin, vmax = -2.5, 2.5
                normalized = np.clip((values - vmin) / (vmax - vmin), 0, 1)
                cmap_name = 'RdBu'
            else:
                vmin, vmax = np.nanpercentile(values[valid_mask], [2, 98])
                if vmax == vmin:
                    normalized = np.ones_like(values) * 0.5
                else:
                    normalized = np.clip((values - vmin) / (vmax - vmin), 0, 1)
                
                cmap_name = 'RdYlBu_r' if variable == 'Tair' else 'Blues'
            
            logging.info(f"🎨 Colormap: {cmap_name}, range: [{vmin:.2f}, {vmax:.2f}]")
            
            # Create RGBA image
            import matplotlib.cm as cm
            cmap = cm.get_cmap(cmap_name)
            rgba = (cmap(normalized) * 255).astype(np.uint8)
            
            # Set invalid pixels to transparent
            rgba[~valid_mask, 3] = 0
            
            img = Image.fromarray(rgba, 'RGBA')
            logging.info(f"✅ Generated tile image: {img.size}, mode: {img.mode}")
        
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
                'X-Tile-Bounds': f'{bounds.north},{bounds.south},{bounds.west},{bounds.east}'
            }
        )
        
    except Exception as e:
        logging.error(f"❌ Tile error {z}/{x}/{y}: {str(e)}", exc_info=True)
        
        # Return transparent tile on error
        img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return Response(
            content=buffer.getvalue(),
            media_type='image/png',
            headers={'X-Error': str(e)[:100]}
        )