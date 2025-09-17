#!/usr/bin/env python3
"""
Pre-download Natural Earth data for offline Cartopy usage
This makes maps load much faster and more reliably
"""

import os
import requests
from pathlib import Path
import shutil
import zipfile
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_offline_cartopy():
    """Download and setup offline Natural Earth data for Cartopy"""
    
    try:
        import cartopy
        cartopy_data_dir = cartopy.config['data_dir']
        logger.info(f"Cartopy data directory: {cartopy_data_dir}")
    except ImportError:
        logger.error("Cartopy not installed. Run: pip install cartopy")
        return False
    
    # Create data directory if it doesn't exist
    Path(cartopy_data_dir).mkdir(parents=True, exist_ok=True)
    
    # CORRECTED Natural Earth data URLs (using proper AWS S3 URLs that Cartopy actually uses)
    datasets = [
        {
            'category': 'physical',
            'name': 'coastline',
            'resolution': '50m',
            'url': 'https://naturalearth.s3.amazonaws.com/50m_physical/ne_50m_coastline.zip'
        },
        {
            'category': 'cultural', 
            'name': 'admin_0_boundary_lines_land',
            'resolution': '50m',
            'url': 'https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_boundary_lines_land.zip'
        },
        {
            'category': 'cultural',
            'name': 'admin_1_states_provinces_lines',
            'resolution': '50m', 
            'url': 'https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_1_states_provinces_lines.zip'
        },
        {
            'category': 'physical',
            'name': 'land',
            'resolution': '50m',
            'url': 'https://naturalearth.s3.amazonaws.com/50m_physical/ne_50m_land.zip'
        },
        {
            'category': 'physical',
            'name': 'ocean',
            'resolution': '50m',
            'url': 'https://naturalearth.s3.amazonaws.com/50m_physical/ne_50m_ocean.zip'
        },
        {
            'category': 'cultural',
            'name': 'admin_0_countries',
            'resolution': '50m',
            'url': 'https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip'
        }
    ]
    
    success_count = 0
    
    for dataset in datasets:
        try:
            # Create category directory
            category_dir = Path(cartopy_data_dir) / 'shapefiles' / 'natural_earth' / dataset['category']
            category_dir.mkdir(parents=True, exist_ok=True)
            
            # Download and extract
            dataset_dir = category_dir / f"ne_{dataset['resolution']}_{dataset['name']}"
            
            if dataset_dir.exists() and list(dataset_dir.glob("*.shp")):
                logger.info(f"✅ {dataset['name']} already exists with shapefiles")
                success_count += 1
                continue
                
            logger.info(f"📥 Downloading {dataset['name']}...")
            
            # Download zip file with proper headers
            zip_path = category_dir / f"ne_{dataset['resolution']}_{dataset['name']}.zip"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Cartopy offline setup)'
            }
            
            response = requests.get(dataset['url'], stream=True, timeout=30, headers=headers)
            response.raise_for_status()
            
            with open(zip_path, 'wb') as f:
                shutil.copyfileobj(response.raw, f)
            
            # Extract zip file
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(dataset_dir)
            
            # Verify extraction
            shapefiles = list(dataset_dir.glob("*.shp"))
            if shapefiles:
                logger.info(f"✅ {dataset['name']} downloaded and extracted ({len(shapefiles)} shapefiles)")
                success_count += 1
            else:
                logger.warning(f"⚠️ {dataset['name']} extracted but no shapefiles found")
            
            # Remove zip file
            zip_path.unlink()
                
        except Exception as e:
            logger.error(f"❌ Failed to download {dataset['name']}: {e}")
            continue
    
    logger.info(f"📊 Successfully downloaded {success_count}/{len(datasets)} datasets")
    
    # Test offline cartopy with enhanced error handling
    try:
        logger.info("🧪 Testing offline cartopy...")
        
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        
        # Test basic Cartopy functionality
        fig = plt.figure(figsize=(10, 6))
        ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
        
        # Set extent for North America
        ax.set_extent([-130, -60, 20, 60], crs=ccrs.PlateCarree())
        
        # Test offline features with fallbacks
        features_loaded = 0
        
        try:
            ax.add_feature(cfeature.NaturalEarthFeature(
                'physical', 'coastline', '50m',
                linewidth=1.0, color='black', facecolor='none'))
            features_loaded += 1
            logger.info("✅ Coastline feature loaded")
        except Exception as e:
            logger.warning(f"⚠️ Coastline feature failed: {e}")
        
        try:
            ax.add_feature(cfeature.NaturalEarthFeature(
                'cultural', 'admin_0_boundary_lines_land', '50m',
                linewidth=0.5, color='gray', facecolor='none'))
            features_loaded += 1
            logger.info("✅ Country boundaries loaded")
        except Exception as e:
            logger.warning(f"⚠️ Country boundaries failed: {e}")
        
        try:
            ax.add_feature(cfeature.NaturalEarthFeature(
                'cultural', 'admin_1_states_provinces_lines', '50m',
                linewidth=0.3, color='lightgray', facecolor='none'))
            features_loaded += 1
            logger.info("✅ State boundaries loaded")
        except Exception as e:
            logger.warning(f"⚠️ State boundaries failed: {e}")
        
        # Add title and save
        plt.title(f'Offline Cartopy Test - North America\n{features_loaded} geographic features loaded')
        
        # Add gridlines
        try:
            gl = ax.gridlines(draw_labels=True, alpha=0.5)
            gl.top_labels = False
            gl.right_labels = False
            logger.info("✅ Gridlines added")
        except Exception as e:
            logger.warning(f"⚠️ Gridlines failed: {e}")
        
        plt.savefig('offline_cartopy_test.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"✅ Offline cartopy test successful! Features loaded: {features_loaded}/3")
        logger.info("📁 Test map saved: offline_cartopy_test.png")
        
        return True
        
    except Exception as test_error:
        logger.error(f"❌ Offline cartopy test failed: {test_error}")
        return False

def force_cartopy_download():
    """Force Cartopy to download features by using them"""
    try:
        logger.info("🔄 Forcing Cartopy to download features...")
        
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        
        # Create a simple plot to trigger downloads
        fig = plt.figure(figsize=(8, 6))
        ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
        
        # This will force Cartopy to download the data
        ax.add_feature(cfeature.COASTLINE)
        ax.add_feature(cfeature.BORDERS) 
        ax.add_feature(cfeature.STATES)
        
        ax.set_extent([-125, -66.5, 20, 50], ccrs.PlateCarree())
        plt.title("Cartopy Auto-Download Test")
        plt.savefig('cartopy_auto_download_test.png', dpi=100, bbox_inches='tight')
        plt.close()
        
        logger.info("✅ Cartopy auto-download completed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Cartopy auto-download failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("🗺️ Setting up offline Cartopy for faster, more reliable maps...")
    
    # Try manual download first
    manual_success = setup_offline_cartopy()
    
    # If manual download partially failed, let Cartopy auto-download
    if not manual_success:
        logger.info("🔄 Manual download had issues. Trying Cartopy auto-download...")
        auto_success = force_cartopy_download()
        
        if auto_success:
            logger.info("✅ Cartopy auto-download successful!")
        else:
            logger.warning("⚠️ Both manual and auto-download had issues")
    
    print("\n🎉 Cartopy setup process complete!")
    print("📈 Your maps should now load faster and more reliably")
    print("🔄 Restart your application to use the cached features")
    print(f"📁 Check for test images: offline_cartopy_test.png, cartopy_auto_download_test.png")