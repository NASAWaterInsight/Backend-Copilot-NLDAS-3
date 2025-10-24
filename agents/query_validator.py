import logging
import re
from typing import Dict, Optional, Tuple

class QueryValidator:
    """
    Validates user queries for the Hydrology Copilot.
    Only validates data/analysis queries. Lets GPT-4 handle general conversation.
    """
    
    # Data query indicators - if these are present, we need parameters
    DATA_QUERY_INDICATORS = [
        'show', 'map', 'plot', 'visualize', 'display', 'chart', 'graph',
        'what is', 'what was', 'tell me', 'how much', 'calculate',
        'average', 'mean', 'max', 'min', 'trend', 'compare', 'analyze',
        'find', 'get', 'give me', 'i want', 'i need'
    ]
    
    # Analysis query indicators - queries that find regions/extremes
    ANALYSIS_INDICATORS = [
        'top', 'hottest', 'coldest', 'warmest', 'wettest', 'driest',
        'most', 'highest', 'lowest', 'extreme', 'worst', 'best',
        'find regions', 'where are', 'which areas', 'significant'
    ]
    
    # Analysis method indicators
    PIXEL_INDICATORS = ['pixel', 'grid', 'exact', 'coordinate', 'lat', 'lon', 'latitude', 'longitude']
    HUC_INDICATORS = ['huc', 'basin', 'watershed', 'hydrologic unit', 'usgs basin']
    
    # Hydrology/weather variables
    VARIABLES = {
        'temperature': ['temperature', 'temp', 'tair', 'hot', 'cold', 'warm', 'cool', 'heat'],
        'precipitation': ['precipitation', 'rain', 'rainfall', 'rainf'],
        'drought': ['drought', 'spi', 'spi3', 'dry', 'dryness'],
        'humidity': ['humidity', 'moisture', 'qair'],
        'wind': ['wind'],
        'pressure': ['pressure', 'psurf'],
        'radiation': ['radiation', 'swdown', 'lwdown', 'solar']
    }
    
    # US regions/states
    REGIONS = [
        'maryland', 'florida', 'california', 'texas', 'michigan', 'alaska',
        'new york', 'ohio', 'pennsylvania', 'illinois', 'arizona',
        'washington', 'oregon', 'nevada', 'utah', 'colorado',
        'conus', 'us', 'usa', 'united states'
    ]
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_query(self, user_query: str) -> Dict:
        """
        Main validation method.
        
        Returns:
        {
            'is_data_query': bool,
            'is_analysis_query': bool,  # NEW: Is this finding regions/extremes?
            'requires_validation': bool,
            'is_valid': bool,
            'missing_params': list,
            'missing_analysis_method': bool,  # NEW: Need to ask about pixel vs HUC?
            'extracted_params': dict,
            'message': str (optional)
        }
        """
        query_lower = user_query.lower().strip()
        
        # Step 1: Determine if this is a data/analysis query
        is_data_query = self._is_data_query(query_lower)
        
        # If it's NOT a data query, let GPT-4 handle it naturally
        if not is_data_query:
            return {
                'is_data_query': False,
                'is_analysis_query': False,
                'requires_validation': False,
                'is_valid': True,
                'missing_params': [],
                'missing_analysis_method': False,
                'extracted_params': {},
                'should_execute_agent': True
            }
        
        # Step 2: Check if this is an ANALYSIS query (finding regions/extremes)
        is_analysis_query = self._is_analysis_query(query_lower)
        
        # Step 3: Extract parameters
        extracted = self._extract_parameters(user_query)
        
        # Step 4: For analysis queries, check if analysis method is specified
        if is_analysis_query:
            has_method = self._has_analysis_method(query_lower)
            
            if not has_method:
                # Ask user to specify analysis method
                return {
                    'is_data_query': True,
                    'is_analysis_query': True,
                    'requires_validation': True,
                    'is_valid': False,
                    'missing_params': [],
                    'missing_analysis_method': True,
                    'extracted_params': extracted,
                    'message': self._generate_analysis_method_message(user_query, extracted),
                    'should_execute_agent': False
                }
        
        # Step 5: Check for missing required parameters
        missing = self._check_missing_parameters(extracted, is_analysis_query)
        
        if missing:
            return {
                'is_data_query': True,
                'is_analysis_query': is_analysis_query,
                'requires_validation': True,
                'is_valid': False,
                'missing_params': missing,
                'missing_analysis_method': False,
                'extracted_params': extracted,
                'message': self._generate_missing_param_message(missing, extracted),
                'should_execute_agent': False
            }
        
        # All good - execute!
        return {
            'is_data_query': True,
            'is_analysis_query': is_analysis_query,
            'requires_validation': True,
            'is_valid': True,
            'missing_params': [],
            'missing_analysis_method': False,
            'extracted_params': extracted,
            'should_execute_agent': True
        }
    
    def _is_data_query(self, query_lower: str) -> bool:
        """Determine if query is asking for data/analysis"""
        for indicator in self.DATA_QUERY_INDICATORS:
            if indicator in query_lower:
                if self._mentions_hydrology_domain(query_lower):
                    return True
        
        if self._mentions_variable(query_lower) and self._mentions_region(query_lower):
            return True
        
        return False
    
    def _is_analysis_query(self, query_lower: str) -> bool:
        """Determine if query is asking to find regions/extremes"""
        return any(indicator in query_lower for indicator in self.ANALYSIS_INDICATORS)
    
    def _has_analysis_method(self, query_lower: str) -> bool:
        """Check if user specified pixel-based or HUC basin-based analysis"""
        has_pixel = any(keyword in query_lower for keyword in self.PIXEL_INDICATORS)
        has_huc = any(keyword in query_lower for keyword in self.HUC_INDICATORS)
        return has_pixel or has_huc
    
    def _mentions_hydrology_domain(self, query_lower: str) -> bool:
        """Check if query mentions hydrology/weather variables or regions"""
        for var_type, keywords in self.VARIABLES.items():
            if any(keyword in query_lower for keyword in keywords):
                return True
        
        if any(region in query_lower for region in self.REGIONS):
            return True
        
        return False
    
    def _mentions_variable(self, query_lower: str) -> bool:
        """Check if query mentions a weather variable"""
        for var_type, keywords in self.VARIABLES.items():
            if any(keyword in query_lower for keyword in keywords):
                return True
        return False
    
    def _mentions_region(self, query_lower: str) -> bool:
        """Check if query mentions a region"""
        return any(region in query_lower for region in self.REGIONS)
    
    def _extract_parameters(self, user_query: str) -> Dict:
        """Extract variable, region, and date from query"""
        query_lower = user_query.lower()
        extracted = {
            'variable': None,
            'region': None,
            'date_period': None,
            'analysis_method': None
        }
        
        # Extract variable
        for var_type, keywords in self.VARIABLES.items():
            if any(keyword in query_lower for keyword in keywords):
                extracted['variable'] = var_type
                break
        
        # Extract region
        for region in self.REGIONS:
            if region in query_lower:
                extracted['region'] = region.title()
                break
        
        # Extract analysis method
        if any(keyword in query_lower for keyword in self.PIXEL_INDICATORS):
            extracted['analysis_method'] = 'pixel'
        elif any(keyword in query_lower for keyword in self.HUC_INDICATORS):
            extracted['analysis_method'] = 'huc'
        
        # Extract date/period
        year_match = re.search(r'(20\d{2})', user_query)
        month_match = re.search(
            r'(january|february|march|april|may|june|july|august|september|october|november|december)',
            query_lower
        )
        day_match = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', user_query)
        
        if year_match or month_match:
            date_parts = []
            if month_match:
                date_parts.append(month_match.group(1).capitalize())
            if day_match and 1 <= int(day_match.group(1)) <= 31:
                date_parts.append(day_match.group(1))
            if year_match:
                date_parts.append(year_match.group(1))
            
            if date_parts:
                extracted['date_period'] = ' '.join(date_parts)
        
        return extracted
    
    def _check_missing_parameters(self, extracted: Dict, is_analysis: bool) -> list:
        """Check which required parameters are missing"""
        missing = []
        
        # For analysis queries, region is optional (they might want all regions)
        # But we still need variable and date
        if not extracted.get('variable'):
            missing.append('variable')
        if not is_analysis and not extracted.get('region'):
            # For non-analysis queries, region is required
            missing.append('region')
        if not extracted.get('date_period'):
            missing.append('date_period')
        
        return missing
    
    def _generate_analysis_method_message(self, user_query: str, extracted: Dict) -> str:
        """Generate message asking user to specify analysis method"""
        variable = extracted.get('variable', 'data')
        region = extracted.get('region', 'the region')
        date = extracted.get('date_period', 'that time period')
        
        return (
            f"I can find the top {variable} regions in {region} for {date}. "
            f"How would you like me to analyze the regions?\n\n"
            f"**Option 1: Pixel-based Analysis** 📍\n"
            f"• Most precise analysis using exact grid coordinates\n"
            f"• Returns specific lat/lon locations\n"
            f"• Best for pinpoint accuracy\n\n"
            f"**Option 2: HUC Basin-based Analysis** 🏞️\n"
            f"• Analysis by USGS Hydrologic Unit Code watersheds\n"
            f"• Returns named basins/watersheds\n"
            f"• Better for water management and hydrological context\n\n"
            f"Please specify: Would you like **pixel-based** or **HUC basin-based** analysis?"
        )
    
    def _generate_missing_param_message(self, missing: list, extracted: Dict) -> str:
        """Generate helpful message about missing parameters"""
        base = "To analyze the data, I need:\n\n"
        
        # Show what we found
        found_parts = []
        if extracted.get('variable'):
            found_parts.append(f"✓ Variable: {extracted['variable']}")
        if extracted.get('region'):
            found_parts.append(f"✓ Region: {extracted['region']}")
        if extracted.get('date_period'):
            found_parts.append(f"✓ Date: {extracted['date_period']}")
        
        if found_parts:
            base += "\n".join(found_parts) + "\n\n"
        
        # Show what's missing
        missing_details = {
            'variable': 'Which variable? (e.g., temperature, precipitation, drought)',
            'region': 'Which region? (e.g., Maryland, California, Texas)',
            'date_period': 'Which time period? (e.g., January 2023, May 15 2023)'
        }
        
        missing_msgs = [f"✗ {missing_details[param]}" for param in missing]
        base += "Still need:\n" + "\n".join(missing_msgs)
        
        return base


# Singleton instance
query_validator = QueryValidator()