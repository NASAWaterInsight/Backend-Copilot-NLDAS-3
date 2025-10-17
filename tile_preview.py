def create_california_tile_preview(variable, date, zoom_level=6):
    """
    Create tile grid preview specifically for California
    """
    
    # California bounds: lat 32.5-42.0, lon -124.4 to -114.1
    # At zoom level 6, California spans roughly these tiles:
    
    if zoom_level == 6:
        # Zoom 6: California coverage
        x_min, x_max = 11, 13  # Longitude range
        y_min, y_max = 22, 25  # Latitude range
    elif zoom_level == 5:
        # Zoom 5: Broader California view
        x_min, x_max = 5, 6
        y_min, y_max = 11, 12
    elif zoom_level == 7:
        # Zoom 7: More detailed California
        x_min, x_max = 22, 27
        y_min, y_max = 44, 51
    else:
        # Default to zoom 6
        x_min, x_max = 11, 13
        y_min, y_max = 22, 25
    
    print(f"🌴 Creating California tile preview at zoom {zoom_level}")
    print(f"📊 Tile range: X={x_min}-{x_max}, Y={y_min}-{y_max}")
    
    # Calculate grid dimensions
    grid_width = x_max - x_min + 1
    grid_height = y_max - y_min + 1
    
    # Create the combined image
    tile_size = 256
    combined_width = grid_width * tile_size
    combined_height = grid_height * tile_size
    
    combined_image = Image.new('RGBA', (combined_width, combined_height), (255, 255, 255, 0))
    
    # Download and place each tile
    successful_tiles = 0
    for x in range(x_min, x_max + 1):
        for y in range(y_min, y_max + 1):
            tile_url = f"http://localhost:8000/api/tiles/{variable}/{date}/{zoom_level}/{x}/{y}.png"
            
            try:
                response = requests.get(tile_url, timeout=10)
                if response.status_code == 200:
                    tile_image = Image.open(io.BytesIO(response.content))
                    
                    # Calculate position in combined image
                    pos_x = (x - x_min) * tile_size
                    pos_y = (y - y_min) * tile_size
                    
                    combined_image.paste(tile_image, (pos_x, pos_y))
                    print(f"✅ Tile {x},{y} added ({response.headers.get('content-length', 'unknown')} bytes)")
                    successful_tiles += 1
                else:
                    print(f"❌ Tile {x},{y} failed: HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"❌ Tile {x},{y} error: {e}")
    
    print(f"📊 Successfully loaded {successful_tiles}/{grid_width * grid_height} tiles")
    
    # Display the result
    plt.figure(figsize=(15, 12))
    plt.imshow(combined_image)
    plt.title(f'California {variable} - {date} (Zoom {zoom_level})\n{grid_width}x{grid_height} tiles', fontsize=16)
    plt.axis('off')
    
    # Save the preview
    filename = f'california_{variable}_{date}_z{zoom_level}_tiles.png'
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"💾 Saved preview as: {filename}")
    
    plt.show()
    
    return combined_image

# Usage examples:
if __name__ == "__main__":
    import requests
    from PIL import Image
    import matplotlib.pyplot as plt
    import io
    
    # Test California temperature tiles
    create_california_tile_preview('Tair', '2023-01-15', zoom_level=6)
    
    # Test different zoom levels
    create_california_tile_preview('Tair', '2023-01-15', zoom_level=5)  # Broader view
    create_california_tile_preview('Tair', '2023-01-15', zoom_level=7)  # More detailed
    
    # Test precipitation
    create_california_tile_preview('Rainf', '2023-01-15', zoom_level=6)