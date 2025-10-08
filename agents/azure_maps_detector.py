import re
from typing import Dict, List, Any, Optional

class AzureMapsDetector:
    """Detector for identifying when user input requires Azure Maps functionality."""
    
    def __init__(self):
        # Keywords that indicate map-related requests
        self.map_keywords = {
            'display': ['show', 'display', 'visualize', 'map', 'plot', 'view', 'see'],
            'search': ['find', 'search', 'locate', 'where', 'location', 'address'],
            'route': ['route', 'path', 'directions', 'navigate', 'travel', 'journey'],
            'area': ['area', 'region', 'boundary', 'zone', 'watershed', 'basin'],
            'coordinates': ['coordinate', 'lat', 'lon', 'latitude', 'longitude', 'gps']
        }
        
        # Geographic and hydrology-specific terms
        self.geo_terms = [
            'river', 'lake', 'stream', 'water', 'hydrology', 'watershed', 'basin',
            'precipitation', 'rainfall', 'flood', 'drought', 'reservoir', 'dam',
            'elevation', 'topography', 'satellite', 'imagery', 'aerial'
        ]
        
        # Coordinate patterns
        self.coordinate_patterns = [
            r'[-+]?\d*\.?\d+[°]?\s*[NS]?\s*[,\s]\s*[-+]?\d*\.?\d+[°]?\s*[EW]?',
            r'[-+]?\d+\.\d+\s*,\s*[-+]?\d+\.\d+',
            r'\b\d{1,3}[°]\d{1,2}[\']\d{1,2}[\"]\s*[NS]\s*\d{1,3}[°]\d{1,2}[\']\d{1,2}[\"]\s*[EW]\b'
        ]
    
    def detect(self, user_input: str) -> Dict[str, Any]:
        """
        Detect if user input requires Azure Maps functionality.
        Only triggers when "azure maps" is explicitly mentioned.
        """
        input_lower = user_input.lower()
        
        # First check if "azure maps" is mentioned
        azure_maps_mentioned = "azure maps" in input_lower
        
        detection_result = {
            'requires_maps': azure_maps_mentioned,
            'confidence': 1.0 if azure_maps_mentioned else 0.0,
            'request_type': None,
            'extracted_data': {},
            'reasoning': []
        }
        
        if not azure_maps_mentioned:
            return detection_result
        
        # If Azure Maps is mentioned, analyze what type of visualization they want
        # Check for map-related keywords
        keyword_matches = self._detect_keywords(input_lower)
        
        # Check for coordinates
        coordinates = self._extract_coordinates(user_input)
        
        # Check for geographic terms
        geo_matches = self._detect_geographic_terms(input_lower)
        
        # Determine request type based on existing logic
        request_type = self._determine_request_type(keyword_matches, input_lower)
        
        # Extract additional data
        extracted_data = self._extract_additional_data(user_input, input_lower)
        
        # Build result
        detection_result.update({
            'requires_maps': True,
            'confidence': 1.0,
            'request_type': request_type,
            'extracted_data': extracted_data
        })
        
        # Add reasoning
        detection_result['reasoning'].append("User explicitly mentioned 'azure maps'")
        if keyword_matches:
            detection_result['reasoning'].append(f"Found analysis keywords: {', '.join(keyword_matches)}")
        if coordinates:
            detection_result['reasoning'].append(f"Found coordinates: {len(coordinates)} sets")
        if geo_matches:
            detection_result['reasoning'].append(f"Found geographic terms: {', '.join(geo_matches)}")
        
        return detection_result
    
    def _detect_keywords(self, input_text: str) -> List[str]:
        """Detect map-related keywords in the input."""
        found_keywords = []
        
        for category, keywords in self.map_keywords.items():
            for keyword in keywords:
                if keyword in input_text:
                    found_keywords.append(keyword)
        
        return found_keywords
    
    def _extract_coordinates(self, input_text: str) -> List[Dict[str, float]]:
        """Extract coordinate pairs from the input text."""
        coordinates = []
        
        for pattern in self.coordinate_patterns:
            matches = re.findall(pattern, input_text, re.IGNORECASE)
            for match in matches:
                coord_pair = self._parse_coordinate_string(match)
                if coord_pair:
                    coordinates.append(coord_pair)
        
        return coordinates
    
    def _parse_coordinate_string(self, coord_string: str) -> Optional[Dict[str, float]]:
        """Parse a coordinate string into lat/lon values."""
        try:
            # Simple decimal degree parsing
            numbers = re.findall(r'[-+]?\d*\.?\d+', coord_string)
            if len(numbers) >= 2:
                lat = float(numbers[0])
                lon = float(numbers[1])
                
                # Basic validation
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return {'latitude': lat, 'longitude': lon}
        except (ValueError, IndexError):
            pass
        
        return None
    
    def _detect_geographic_terms(self, input_text: str) -> List[str]:
        """Detect geographic and hydrology-specific terms."""
        found_terms = []
        
        for term in self.geo_terms:
            if term in input_text:
                found_terms.append(term)
        
        return found_terms
    
    def _calculate_confidence(self, keywords: List[str], coordinates: List[Dict], 
                            geo_terms: List[str]) -> float:
        """Calculate confidence score for map requirement detection."""
        score = 0.0
        
        # Keywords contribute to confidence
        if keywords:
            score += min(len(keywords) * 0.2, 0.6)
        
        # Coordinates strongly indicate map requirement
        if coordinates:
            score += min(len(coordinates) * 0.3, 0.7)
        
        # Geographic terms add context
        if geo_terms:
            score += min(len(geo_terms) * 0.1, 0.3)
        
        return min(score, 1.0)
    
    def _determine_request_type(self, keywords: List[str], input_text: str) -> Optional[str]:
        """Determine the type of map request based on keywords and context."""
        type_scores = {
            'display': 0,
            'search': 0,
            'route': 0
        }
        
        # Score based on keyword categories
        for category, category_keywords in self.map_keywords.items():
            if category in type_scores:
                for keyword in keywords:
                    if keyword in category_keywords:
                        type_scores[category] += 1
        
        # Context-based scoring
        if any(word in input_text for word in ['show', 'display', 'visualize', 'plot']):
            type_scores['display'] += 2
        
        if any(word in input_text for word in ['find', 'search', 'where', 'locate']):
            type_scores['search'] += 2
        
        if any(word in input_text for word in ['route', 'directions', 'path']):
            type_scores['route'] += 2
        
        # Return type with highest score
        if max(type_scores.values()) > 0:
            return max(type_scores, key=type_scores.get)
        
        return 'display'  # Default to display if unclear
    
    def _extract_additional_data(self, original_input: str, lower_input: str) -> Dict[str, Any]:
        """Extract additional data that might be useful for map generation."""
        data = {}
        
        # Extract coordinates
        coordinates = self._extract_coordinates(original_input)
        if coordinates:
            data['coordinates'] = coordinates
        
        # Extract location names (simple approach)
        location_indicators = ['in ', 'at ', 'near ', 'around ', 'from ', 'to ']
        for indicator in location_indicators:
            if indicator in lower_input:
                parts = lower_input.split(indicator)
                if len(parts) > 1:
                    # Extract potential location name (next few words)
                    location_part = parts[1].split()[:3]  # Take up to 3 words
                    if location_part:
                        data.setdefault('locations', []).append(' '.join(location_part))
        
        # Extract numeric values (could be measurements, elevations, etc.)
        numbers = re.findall(r'\d+\.?\d*', original_input)
        if numbers:
            data['numeric_values'] = [float(n) for n in numbers if '.' in n or len(n) <= 4]
        
        # Extract style preferences
        style_keywords = {
            'satellite': ['satellite', 'aerial', 'imagery'],
            'road': ['road', 'street', 'navigation'],
            'terrain': ['terrain', 'elevation', 'topographic', 'topo']
        }
        
        for style, keywords in style_keywords.items():
            if any(keyword in lower_input for keyword in keywords):
                data['preferred_style'] = style
                break
        
        return data
    
    def get_map_request_template(self, detection_result: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a map request template based on detection results."""
        if not detection_result['requires_maps']:
            return {}
        
        template = {
            'type': detection_result['request_type'] or 'display',
            'coordinates': [],
            'data_points': [],
            'style': 'satellite',
            'analysis_type': self._determine_analysis_type(detection_result['extracted_data'])
        }
        
        # Add extracted data
        extracted = detection_result['extracted_data']
        
        if 'coordinates' in extracted:
            template['coordinates'] = [(c['longitude'], c['latitude']) for c in extracted['coordinates']]
        
        if 'locations' in extracted:
            template['search_locations'] = extracted['locations']
        
        if 'preferred_style' in extracted:
            template['style'] = extracted['preferred_style']
        
        return template
    
    def _determine_analysis_type(self, extracted_data: Dict[str, Any]) -> str:
        """Determine what type of weather analysis is needed."""
        # This helps the Azure Maps agent know what data to fetch
        # Options: 'single_map', 'time_series', 'animation', 'comparison'
        
        # You can expand this logic based on keywords in the original query
        return 'single_map'  # Default for now