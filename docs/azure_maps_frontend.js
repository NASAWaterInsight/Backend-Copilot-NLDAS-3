class AzureMapsRenderer {
    constructor(subscriptionKey) {
        this.subscriptionKey = subscriptionKey;
        this.map = null;
        this.dataSources = new Map();
        this.heatMapLayer = null;
        this.imageLayer = null;
        this.pointLayer = null;
    }

    /**
     * Initialize the Azure Maps control
     * @param {string} containerId - ID of the container element
     * @param {Object} config - Map configuration object
     */
    initializeMap(containerId, config) {
        // Initialize the map
        this.map = new atlas.Map(containerId, {
            center: config.center || [0, 0],
            zoom: config.zoom || 10,
            style: config.style || 'satellite',
            authOptions: {
                authType: 'subscriptionKey',
                subscriptionKey: this.subscriptionKey
            }
        });

        // Wait for map to load
        this.map.events.add('ready', () => {
            this.addDataSources(config.data_sources || []);
            this.addLayers(config.layers || []);
        });
    }

    /**
     * Initialize map with weather data and PNG overlay from backend
     * @param {string} containerId - ID of the container element
     * @param {Object} weatherResponse - Response from Azure Maps agent with overlay_url
     */
    initializeWeatherMap(containerId, weatherResponse) {
        const config = weatherResponse.data.map_config;
        const overlayUrl = weatherResponse.data.overlay_url;
        
        console.log('Initializing Azure Maps with PNG overlay:', overlayUrl);
        
        // Initialize the map
        this.map = new atlas.Map(containerId, {
            center: config.center,
            zoom: config.zoom,
            style: config.style,
            authOptions: {
                authType: 'subscriptionKey',
                subscriptionKey: this.subscriptionKey
            }
        });

        // Wait for map to load then add both overlay and interactive points
        this.map.events.add('ready', () => {
            if (overlayUrl) {
                this.addPNGOverlay(overlayUrl, weatherResponse.data.weather_data);
            }
            this.addInteractivePoints(config);
            this.addLegend(config.legend, config.color_scheme, config.value_range);
        });
    }

    /**
     * Add data sources to the map
     * @param {Array} dataSources - Array of data source configurations
     */
    addDataSources(dataSources) {
        dataSources.forEach(sourceConfig => {
            let dataSource;
            
            if (sourceConfig.type === 'geojson') {
                dataSource = new atlas.source.DataSource(sourceConfig.id);
                dataSource.add(sourceConfig.data);
            }
            
            this.map.sources.add(dataSource);
            this.dataSources.set(sourceConfig.id, dataSource);
        });
    }

    /**
     * Add layers to the map
     * @param {Array} layers - Array of layer configurations
     */
    addLayers(layers) {
        layers.forEach(layerConfig => {
            let layer;
            
            switch (layerConfig.type) {
                case 'symbol':
                    layer = new atlas.layer.SymbolLayer(
                        this.dataSources.get(layerConfig.source),
                        layerConfig.id,
                        layerConfig.options
                    );
                    break;
                case 'line':
                    layer = new atlas.layer.LineLayer(
                        this.dataSources.get(layerConfig.source),
                        layerConfig.id,
                        layerConfig.options
                    );
                    break;
                case 'polygon':
                    layer = new atlas.layer.PolygonLayer(
                        this.dataSources.get(layerConfig.source),
                        layerConfig.id,
                        layerConfig.options
                    );
                    break;
            }
            
            if (layer) {
                this.map.layers.add(layer);
            }
        });
    }

    /**
     * Add PNG overlay image to the map with EXACT geographic coordinates
     * @param {string} overlayUrl - URL to the georeferenced PNG overlay
     * @param {Object} weatherData - Weather data with coordinate bounds
     */
    addPNGOverlay(overlayUrl, weatherData) {
        try {
            // CRITICAL: Get EXACT bounds from weather data
            const lons = weatherData.longitude;
            const lats = weatherData.latitude;
            
            // Calculate precise geographic bounds
            const west = Math.min(...lons);
            const east = Math.max(...lons);
            const south = Math.min(...lats);
            const north = Math.max(...lats);
            
            console.log('🗺️ Adding temperature overlay:');
            console.log(`   West: ${west.toFixed(6)}°`);
            console.log(`   East: ${east.toFixed(6)}°`);
            console.log(`   South: ${south.toFixed(6)}°`);
            console.log(`   North: ${north.toFixed(6)}°`);
            console.log(`   Overlay URL: ${overlayUrl}`);
            
            // CRITICAL: Create ImageLayer with EXACT geographic coordinates
            // FIXED: Use higher opacity for better visibility
            this.imageLayer = new atlas.layer.ImageLayer({
                url: overlayUrl,
                coordinates: [
                    [west, north],  // Top-left corner: [west, north]
                    [east, north],  // Top-right corner: [east, north]
                    [east, south],  // Bottom-right corner: [east, south]
                    [west, south]   // Bottom-left corner: [west, south]
                ],
                opacity: 0.9  // INCREASED from 0.75 to 0.9 for better visibility
            });
            
            // Add layer to map
            this.map.layers.add(this.imageLayer);
            
            console.log('✅ Temperature overlay added with high opacity for visibility');
            console.log('📍 Image coordinates match data bounds exactly');
            
            // Test the image loading
            const img = new Image();
            img.onload = () => {
                console.log('✅ Overlay image loaded successfully');
                console.log(`📐 Image dimensions: ${img.width}x${img.height}`);
            };
            img.onerror = () => {
                console.error('❌ Failed to load overlay image');
            };
            img.src = overlayUrl;
            
            // OPTIONAL: Fit map view to overlay bounds with small padding
            this.map.setCamera({
                bounds: [west, south, east, north],
                padding: 50
            });
            
        } catch (error) {
            console.error('❌ Failed to add temperature overlay:', error);
        }
    }

    /**
     * Add GeoTIFF overlay to the map (if supported)
     * @param {string} geotiffUrl - URL to the GeoTIFF file
     * @param {Array} bounds - Bounds array [west, south, east, north]
     */
    addGeoTIFFOverlay(geotiffUrl, bounds) {
        try {
            console.log('🌍 Adding GeoTIFF overlay (experimental)');
            
            // For now, Azure Maps doesn't natively support GeoTIFF
            // We can either:
            // 1. Convert GeoTIFF to PNG on client side (complex)
            // 2. Use the GeoTIFF as a regular image (loses georeferencing)
            // 3. Process GeoTIFF server-side to PNG (recommended)
            
            console.warn('⚠️ GeoTIFF overlay not fully supported yet. Using as regular image.');
            
            // Fallback: treat as regular image
            this.imageLayer = new atlas.layer.ImageLayer({
                url: geotiffUrl,
                coordinates: [
                    [bounds[0], bounds[3]], // top-left: [west, north]
                    [bounds[2], bounds[3]], // top-right: [east, north]
                    [bounds[2], bounds[1]], // bottom-right: [east, south]
                    [bounds[0], bounds[1]]  // bottom-left: [west, south]
                ],
                opacity: 0.7
            });
            
            this.map.layers.add(this.imageLayer);
            
            console.log('✅ GeoTIFF overlay added as image layer');
            
        } catch (error) {
            console.error('❌ Failed to add GeoTIFF overlay:', error);
        }
    }

    /**
     * Add interactive data points for hover functionality
     * @param {Object} config - Map configuration with sampled data points
     */
    addInteractivePoints(config) {
        if (!config.data_points || config.data_points.length === 0) {
            return;
        }
        
        // Create data source for interactive points
        const pointDataSource = new atlas.source.DataSource();
        
        // Convert data points to atlas Point features (invisible points for interaction)
        const features = config.data_points.map(point => {
            return new atlas.data.Feature(
                new atlas.data.Point([point.longitude, point.latitude]),
                {
                    value: point.value,
                    title: point.title
                }
            );
        });
        
        pointDataSource.add(features);
        this.map.sources.add(pointDataSource);
        
        // Create invisible symbol layer for hover interaction
        this.pointLayer = new atlas.layer.SymbolLayer(pointDataSource, null, {
            iconOptions: {
                image: 'marker-red',
                size: 0.1, // Very small, nearly invisible
                opacity: 0.1
            }
        });
        
        this.map.layers.add(this.pointLayer);
        
        // Add hover functionality
        this.addWeatherPopups(pointDataSource);
        
        console.log(`✅ Added ${config.data_points.length} interactive points`);
    }

    /**
     * Add weather data as heat map to the map
     * @param {Object} config - Map configuration with weather data
     */
    addWeatherData(config) {
        // Create data source for heat map
        const heatMapDataSource = new atlas.source.DataSource();
        
        // Convert data points to atlas Point features
        const features = config.data_points.map(point => {
            return new atlas.data.Feature(
                new atlas.data.Point([point.longitude, point.latitude]),
                {
                    value: point.value,
                    title: point.title
                }
            );
        });
        
        heatMapDataSource.add(features);
        this.map.sources.add(heatMapDataSource);
        
        // Create heat map layer
        const heatMapLayer = new atlas.layer.HeatMapLayer(heatMapDataSource, null, {
            radius: config.heat_map_config.radius,
            opacity: config.heat_map_config.opacity,
            intensity: config.heat_map_config.intensity,
            color: this.getColorGradient(config.color_scheme, config.value_range)
        });
        
        this.map.layers.add(heatMapLayer);
        this.heatMapLayer = heatMapLayer;
        
        // Add legend
        this.addLegend(config.legend, config.color_scheme, config.value_range);
        
        // Add popup for data points
        this.addWeatherPopups(heatMapDataSource);
    }

    /**
     * Add popups for weather data points (updated for overlay mode)
     * @param {atlas.source.DataSource} dataSource - Data source with weather points
     */
    addWeatherPopups(dataSource) {
        const popup = new atlas.Popup({
            pixelOffset: [0, -10],
            closeButton: false
        });

        // Add hover event to the invisible point layer
        this.map.events.add('mouseover', this.pointLayer, (e) => {
            if (e.shapes && e.shapes.length > 0) {
                const properties = e.shapes[0].getProperties();
                const coordinates = e.shapes[0].getCoordinates();
                
                popup.setOptions({
                    content: `
                        <div style="padding: 8px; background: rgba(0,0,0,0.8); color: white; border-radius: 4px;">
                            <div style="font-weight: bold; margin-bottom: 4px;">${properties.title}</div>
                            <div style="font-size: 11px; opacity: 0.9;">
                                Lat: ${coordinates[1].toFixed(4)}°<br>
                                Lon: ${coordinates[0].toFixed(4)}°
                            </div>
                        </div>
                    `,
                    position: coordinates
                });
                popup.open(this.map);
            }
        });

        this.map.events.add('mouseleave', this.pointLayer, () => {
            popup.close();
        });
    }

    /**
     * Get color gradient based on weather variable type
     * @param {string} colorScheme - Type of color scheme needed
     * @param {Array} valueRange - Min and max values
     */
    getColorGradient(colorScheme, valueRange) {
        switch (colorScheme) {
            case 'temperature':
                return [
                    'interpolate',
                    ['linear'],
                    ['heatmap-density'],
                    0, 'rgba(0, 0, 255, 0)',      // Cold - Blue
                    0.2, 'rgba(0, 100, 255, 1)',
                    0.4, 'rgba(0, 255, 255, 1)',  // Cool - Cyan
                    0.6, 'rgba(255, 255, 0, 1)',  // Warm - Yellow
                    0.8, 'rgba(255, 100, 0, 1)',  // Hot - Orange
                    1, 'rgba(255, 0, 0, 1)'       // Very Hot - Red
                ];
            
            case 'precipitation':
                return [
                    'interpolate',
                    ['linear'],
                    ['heatmap-density'],
                    0, 'rgba(255, 255, 255, 0)',  // No precipitation - Transparent
                    0.2, 'rgba(200, 200, 255, 1)', // Light - Light Blue
                    0.4, 'rgba(100, 150, 255, 1)', // Moderate - Blue
                    0.6, 'rgba(0, 100, 255, 1)',   // Heavy - Dark Blue
                    0.8, 'rgba(0, 50, 200, 1)',    // Very Heavy - Navy
                    1, 'rgba(0, 0, 150, 1)'        // Extreme - Dark Navy
                ];
            
            case 'drought':
                return [
                    'interpolate',
                    ['linear'],
                    ['heatmap-density'],
                    0, 'rgba(139, 0, 0, 1)',       // Extreme Drought - Dark Red
                    0.25, 'rgba(255, 0, 0, 1)',    // Severe Drought - Red
                    0.4, 'rgba(255, 165, 0, 1)',   // Moderate Drought - Orange
                    0.5, 'rgba(255, 255, 255, 0)', // Normal - Transparent
                    0.6, 'rgba(173, 216, 230, 1)', // Mild Wet - Light Blue
                    0.75, 'rgba(0, 191, 255, 1)',  // Moderate Wet - Deep Sky Blue
                    1, 'rgba(0, 0, 255, 1)'        // Extreme Wet - Blue
                ];
            
            default:
                return [
                    'interpolate',
                    ['linear'],
                    ['heatmap-density'],
                    0, 'rgba(0, 0, 255, 0)',
                    0.5, 'rgba(0, 255, 0, 1)',
                    1, 'rgba(255, 0, 0, 1)'
                ];
        }
    }

    /**
     * Add legend for the overlay (updated styling)
     * @param {Object} legend - Legend configuration
     * @param {string} colorScheme - Color scheme type
     * @param {Array} valueRange - Value range for the legend
     */
    addLegend(legend, colorScheme, valueRange) {
        // Create legend HTML with better styling for overlay mode
        const legendHtml = `
            <div id="weather-legend" style="
                position: absolute;
                top: 10px;
                right: 10px;
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                font-family: 'Segoe UI', Arial, sans-serif;
                min-width: 220px;
                border: 1px solid rgba(255,255,255,0.2);
            ">
                <h4 style="margin: 0 0 8px 0; font-size: 14px; font-weight: bold;">${legend.title}</h4>
                <div style="font-size: 11px; color: #ccc; margin-bottom: 12px; opacity: 0.9;">
                    📅 ${legend.date} | 📍 ${legend.region}
                </div>
                <div style="margin-bottom: 8px; font-size: 10px; color: #aaa;">
                    🗺️ PNG Overlay + Interactive Points
                </div>
                <div id="legend-gradient" style="
                    height: 20px;
                    background: ${this.getLegendGradient(colorScheme)};
                    border: 1px solid rgba(255,255,255,0.3);
                    margin-bottom: 8px;
                    border-radius: 3px;
                "></div>
                <div style="display: flex; justify-content: space-between; font-size: 10px; color: #ddd;">
                    <span>${valueRange[0].toFixed(1)}</span>
                    <span>${valueRange[1].toFixed(1)}</span>
                </div>
                <div style="margin-top: 8px; font-size: 9px; color: #999; text-align: center;">
                    Hover over map for details
                </div>
            </div>
        `;
        
        // Add legend to map container
        const mapContainer = this.map.getMapContainer();
        const legendDiv = document.createElement('div');
        legendDiv.innerHTML = legendHtml;
        mapContainer.appendChild(legendDiv);
    }

    /**
     * Add popup functionality to markers
     * @param {string} layerId - ID of the symbol layer
     */
    addPopups(layerId) {
        const popup = new atlas.Popup({
            pixelOffset: [0, -18],
            closeButton: false
        });

        this.map.events.add('mouseover', layerId, (e) => {
            if (e.shapes && e.shapes.length > 0) {
                const properties = e.shapes[0].getProperties();
                popup.setOptions({
                    content: `
                        <div style="padding: 10px;">
                            <h4>${properties.title || 'Location'}</h4>
                            <p>${properties.description || ''}</p>
                            ${properties.value ? `<p><strong>Value:</strong> ${properties.value}</p>` : ''}
                        </div>
                    `,
                    position: e.shapes[0].getCoordinates()
                });
                popup.open(this.map);
            }
        });

        this.map.events.add('mouseleave', layerId, () => {
            popup.close();
        });
    }

    /**
     * Update map with new configuration
     * @param {Object} config - New map configuration
     */
    updateMap(config) {
        if (config.center) {
            this.map.setCamera({ center: config.center });
        }
        if (config.zoom) {
            this.map.setCamera({ zoom: config.zoom });
        }
        
        // Clear existing data sources and layers
        this.map.layers.clear();
        this.map.sources.clear();
        this.dataSources.clear();
        
        // Add new data sources and layers
        this.addDataSources(config.data_sources || []);
        this.addLayers(config.layers || []);
    }

    /**
     * Update weather data with new overlay
     * @param {Object} weatherResponse - New weather data from backend
     */
    updateWeatherData(weatherResponse) {
        // Clear existing layers
        if (this.imageLayer) {
            this.map.layers.remove(this.imageLayer);
            this.imageLayer = null;
        }
        
        if (this.pointLayer) {
            this.map.layers.remove(this.pointLayer);
            this.pointLayer = null;
        }
        
        // Clear existing sources
        this.map.sources.clear();
        
        // Clear existing legend
        const existingLegend = document.getElementById('weather-legend');
        if (existingLegend) {
            existingLegend.remove();
        }
        
        // Add new overlay and data
        const config = weatherResponse.data.map_config;
        const overlayUrl = weatherResponse.data.overlay_url;
        
        if (overlayUrl) {
            this.addPNGOverlay(overlayUrl, weatherResponse.data.weather_data);
        }
        this.addInteractivePoints(config);
        this.addLegend(config.legend, config.color_scheme, config.value_range);
    }

    /**
     * Add search functionality
     * @param {string} inputId - ID of the search input element
     */
    addSearchBox(inputId) {
        const searchInput = document.getElementById(inputId);
        if (!searchInput) return;

        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.searchLocation(searchInput.value);
            }
        });
    }

    /**
     * Search for a location and center map on result
     * @param {string} query - Search query
     */
    async searchLocation(query) {
        try {
            const response = await fetch(`/api/maps/search`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    type: 'search',
                    query: query
                })
            });
            
            const result = await response.json();
            
            if (result.results && result.results.length > 0) {
                const location = result.results[0];
                const coordinates = [
                    location.position.lon,
                    location.position.lat
                ];
                
                this.map.setCamera({
                    center: coordinates,
                    zoom: 15
                });
                
                // Add marker for search result
                const dataSource = new atlas.source.DataSource();
                dataSource.add(new atlas.data.Point(coordinates));
                this.map.sources.add(dataSource);
                
                const layer = new atlas.layer.SymbolLayer(dataSource, null, {
                    iconOptions: {
                        image: 'pin-red'
                    }
                });
                this.map.layers.add(layer);
            }
        } catch (error) {
            console.error('Search failed:', error);
        }
    }

    /**
     * Fit map to show all data points
     */
    fitToData() {
        const bounds = new atlas.data.BoundingBox.fromData(
            Array.from(this.dataSources.values()).map(ds => ds.toJson())
        );
        
        this.map.setCamera({
            bounds: bounds,
            padding: 50
        });
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AzureMapsRenderer;
}