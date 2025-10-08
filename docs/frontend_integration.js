// Add this to your main frontend JavaScript file

async function handleUserQuery() {
    const query = document.getElementById('search-input').value;
    
    try {
        const response = await fetch('/api/multi_agent_function', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });
        
        const result = await response.json();
        console.log('Full backend response:', result); // Debug log
        
        // CHECK: Is this an Azure Maps response?
        if (result.response && result.response.data_type === 'azure_maps_interactive') {
            console.log('🗺️ Detected Azure Maps response with PNG overlay, initializing map...');
            console.log('Overlay URL:', result.response.overlay_url);
            
            // Make sure you have the Azure Maps renderer available
            if (typeof AzureMapsRenderer === 'undefined') {
                console.error('❌ AzureMapsRenderer not loaded! Include azure_maps_frontend.js');
                document.getElementById('result-container').innerHTML = 
                    '<p>Error: Azure Maps frontend not loaded. Please include azure_maps_frontend.js</p>';
                return;
            }
            
            // Initialize Azure Maps with YOUR actual subscription key
            const azureMapsKey = 'YOUR_ACTUAL_AZURE_MAPS_SUBSCRIPTION_KEY'; // REPLACE THIS!
            const renderer = new AzureMapsRenderer(azureMapsKey);
            
            // Clear previous results and create map container
            document.getElementById('result-container').innerHTML = 
                '<div id="azure-map-container" style="width: 100%; height: 600px; border: 1px solid #ccc; border-radius: 8px;"></div>';
            
            // Initialize the weather map with PNG overlay
            renderer.initializeWeatherMap('azure-map-container', result.response);
            
            // Show success message with overlay info
            setTimeout(() => {
                const statusDiv = document.createElement('div');
                statusDiv.innerHTML = `
                    <div style="margin-top: 10px; padding: 10px; background: #e8f5e8; border: 1px solid #4caf50; border-radius: 4px;">
                        ✅ <strong>Azure Maps Interactive Visualization Ready</strong><br>
                        📊 Transparent PNG overlay with ${result.response.weather_data.longitude.length} data points<br>
                        🗺️ Hover over the map for detailed values
                    </div>
                `;
                document.getElementById('result-container').appendChild(statusDiv);
            }, 2000);
            
        } else if (result.response && result.response.content) {
            // Handle regular responses (PNG images, text)
            if (result.response.content.startsWith('http')) {
                // It's an image URL
                document.getElementById('result-container').innerHTML = 
                    `<img src="${result.response.content}" style="max-width: 100%; height: auto;" />`;
            } else {
                // It's text content
                document.getElementById('result-container').innerHTML = 
                    `<p>${result.response.content}</p>`;
            }
        } else {
            console.error('Unexpected response format:', result);
            document.getElementById('result-container').innerHTML = 
                '<p>Unexpected response format. Check console for details.</p>';
        }
        
    } catch (error) {
        console.error('Query failed:', error);
        document.getElementById('result-container').innerHTML = 
            `<p>Error: ${error.message}</p>`;
    }
}
