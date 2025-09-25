#!/bin/bash

echo "🔧 Installing Cartopy and dependencies..."

cd /Users/mghaziza/Library/CloudStorage/OneDrive-NASA/hydrology-copilot-backend

# Install dependencies first
echo "📦 Installing dependencies..."
pip install proj pyproj shapely

# Install cartopy
echo "📦 Installing Cartopy..."
pip install cartopy

# Install additional geospatial packages
echo "📦 Installing additional geospatial packages..."
pip install geopandas fiona

echo "🧪 Testing Cartopy installation..."
python3 -c "
import sys
print(f'Python version: {sys.version}')

try:
    import cartopy
    print(f'✅ Cartopy version: {cartopy.__version__}')
    
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    
    print('✅ Cartopy imports successful')
    
    # Test basic plot with enhanced visibility
    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
    
    # Set extent for Florida (your test region)
    ax.set_extent([-87.6, -80.0, 24.5, 31.0], crs=ccrs.PlateCarree())
    
    # Test different features with enhanced visibility
    features_working = []
    try:
        ax.add_feature(cfeature.COASTLINE, color='red', linewidth=2, alpha=1.0)
        features_working.append('COASTLINE (red)')
        print('✅ COASTLINE added (red, thick)')
    except Exception as e:
        print(f'❌ COASTLINE failed: {e}')
    
    try:
        ax.add_feature(cfeature.BORDERS, color='blue', linewidth=1.5, alpha=1.0)
        features_working.append('BORDERS (blue)')
        print('✅ BORDERS added (blue)')
    except Exception as e:
        print(f'❌ BORDERS failed: {e}')
    
    try:
        ax.add_feature(cfeature.STATES, color='green', linewidth=1, alpha=1.0)
        features_working.append('STATES (green)')
        print('✅ STATES added (green)')
    except Exception as e:
        print(f'❌ STATES failed: {e}')
    
    # Add gridlines
    try:
        gl = ax.gridlines(draw_labels=True, alpha=0.7, color='black')
        gl.top_labels = False
        gl.right_labels = False
        features_working.append('GRIDLINES')
        print('✅ GRIDLINES added')
    except Exception as e:
        print(f'❌ GRIDLINES failed: {e}')
    
    plt.title(f'Cartopy Installation Test - Florida\\n{len(features_working)} features working: {features_working}')
    plt.savefig('cartopy_installation_test.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f'✅ Test plot saved: cartopy_installation_test.png')
    print(f'📊 Working features ({len(features_working)}): {features_working}')
    
    if len(features_working) >= 2:
        print('🎉 Cartopy installation successful with geographic features!')
    else:
        print('⚠️ Cartopy installed but geographic features may need internet connection')
    
except ImportError as e:
    print(f'❌ Cartopy installation failed: {e}')
    exit(1)
except Exception as e:
    print(f'❌ Cartopy test failed: {e}')
    exit(1)
"

echo ""
echo "✅ Cartopy installation complete!"
echo "🔍 Check cartopy_installation_test.png to see if geographic features are visible"
echo ""
echo "📋 Next steps:"
echo "  1. Check the generated test image"
echo "  2. If you see coastlines/borders, Cartopy is working!"
echo "  3. If no geographic features, run: python setup_offline_cartopy.py"
echo "  4. Restart your Azure Functions: func start --no-build"
