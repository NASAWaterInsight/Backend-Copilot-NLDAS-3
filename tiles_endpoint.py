from fastapi import APIRouter, Response, HTTPException
import mercantile
import numpy as np
from PIL import Image
import io
import logging
import time

router = APIRouter()

from agents.weather_tool import (
    load_specific_date_kerchunk,
    load_specific_month_spi_kerchunk,
    get_account_key,
    ACCOUNT_NAME
)

@router.get("/tiles/{variable}/{date}/{z}/{x}/{y}.png")
async def get_weather_tile(
    variable: str,  # 'Tair', 'Rainf', 'SPI3'
    date: str,      # '2023-05-12' or '2023-05' for SPI
    z: int,         # Zoom level (3-10)
    x: int,         # Tile X coordinate
    y: int          # Tile Y coordinate
):
    """
    Generate a 256x256 weather tile using TiTiler approach
    
    Each tile has EXACT bounds that match Azure Maps expectations
    """
    try:
        logging.info(f"🗺️ Generating tile: {variable}/{date}/{z}/{x}/{y}")
        
        # Step 1: Get EXACT tile bounds using Mercantile (same as Azure Maps)
        tile = mercantile.Tile(x, y, z)
        bounds = mercantile.bounds(tile)
        
        logging.info(f"📍 Tile bounds: {bounds.south:.6f},{bounds.west:.6f} to {bounds.north:.6f},{bounds.east:.6f}")
        
        # Step 2: Parse date and load data
        date_parts = date.split('-')
        year = int(date_parts[0])
        month = int(date_parts[1])
        
        account_key = get_account_key()
        
        if variable == 'SPI3':
            # Monthly SPI data
            ds, _ = load_specific_month_spi_kerchunk(ACCOUNT_NAME, account_key, year, month)
            data = ds[variable].sel(
                latitude=slice(bounds.south, bounds.north),
                longitude=slice(bounds.west, bounds.east)
            )
        else:
            # Daily data
            day = int(date_parts[2])
            ds, _ = load_specific_date_kerchunk(ACCOUNT_NAME, account_key, year, month, day)
            data = ds[variable].sel(
                lat=slice(bounds.south, bounds.north),
                lon=slice(bounds.west, bounds.east)
            )
            
            if variable == 'Tair':
                data = data.mean(dim='time') - 273.15
            elif variable == 'Rainf':
                data = data.sum(dim='time')
            else:
                data = data.mean(dim='time')
        
        # Step 3: Generate 256x256 tile image
        if hasattr(data, 'squeeze'):
            data = data.squeeze()
        
        values = data.values
        
        if values.size == 0 or not np.isfinite(values).any():
            # Return transparent tile
            img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        else:
            # Resample to exact 256x256
            from scipy.ndimage import zoom
            if values.shape != (256, 256):
                zoom_y = 256 / values.shape[0] if values.shape[0] > 0 else 1
                zoom_x = 256 / values.shape[1] if values.shape[1] > 0 else 1
                values = zoom(values, (zoom_y, zoom_x), order=1)
            
            # Apply colormap
            valid_mask = np.isfinite(values)
            if not valid_mask.any():
                img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
            else:
                # Normalize and color
                if variable == 'SPI3':
                    # Fixed SPI scale
                    normalized = np.clip((values + 2.5) / 5.0, 0, 1)
                    cmap_name = 'RdBu'
                else:
                    vmin, vmax = np.nanmin(values), np.nanmax(values)
                    if vmax == vmin:
                        normalized = np.ones_like(values) * 0.5
                    else:
                        normalized = (values - vmin) / (vmax - vmin)
                    
                    cmap_name = 'RdYlBu_r' if variable == 'Tair' else 'Blues'
                
                # Create RGBA image
                import matplotlib.cm as cm
                cmap = cm.get_cmap(cmap_name)
                rgba = (cmap(normalized) * 255).astype(np.uint8)
                rgba[~valid_mask, 3] = 0  # Transparent for NaN
                
                img = Image.fromarray(rgba, 'RGBA')
        
        # Step 4: Return tile
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        
        ds.close()
        
        return Response(
            content=buffer.getvalue(),
            media_type='image/png',
            headers={
                'Cache-Control': 'public, max-age=86400',  # Cache for 1 day
                'Access-Control-Allow-Origin': '*'
            }
        )
        
    except Exception as e:
        logging.error(f"❌ Tile generation error for {z}/{x}/{y}: {e}")
        # Return transparent tile on error
        img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return Response(content=buffer.getvalue(), media_type='image/png')

@router.get("/tiles/health")
async def tiles_health():
    """Health check for tiles endpoint"""
    return {"status": "healthy", "service": "weather-tiles"}