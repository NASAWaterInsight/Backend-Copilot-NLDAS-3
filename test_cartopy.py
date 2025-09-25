#!/usr/bin/env python3

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def test_cartopy():
    print("Testing Cartopy installation...")
    
    try:
        import cartopy
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        
        print(f"✅ Cartopy {cartopy.__version__} imported successfully")
        
        # Test basic functionality
        fig = plt.figure(figsize=(10, 6))
        ax = fig.add_subplot(111, projection=ccrs.PlateCarree())
        
        # Add features - ONLY LINES, NO FILLS
        ax.add_feature(cfeature.COASTLINE)
        ax.add_feature(cfeature.BORDERS)
        ax.add_feature(cfeature.STATES)
        
        # Set extent for Seattle area
        ax.set_extent([-123, -121, 47, 48], crs=ccrs.PlateCarree())
        
        # Add gridlines
        gl = ax.gridlines(draw_labels=True)
        gl.top_labels = False
        gl.right_labels = False
        
        plt.title('Cartopy Test - Seattle Area')
        plt.savefig('cartopy_test.png', dpi=150, bbox_inches='tight')
        print("✅ Test map saved as 'cartopy_test.png'")
        
        return True
        
    except ImportError as e:
        print(f"❌ Cartopy import failed: {e}")
        print("💡 Install with: pip install cartopy")
        return False
    except Exception as e:
        print(f"❌ Cartopy test failed: {e}")
        return False

if __name__ == "__main__":
    test_cartopy()
