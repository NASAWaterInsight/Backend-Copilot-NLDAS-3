# agents/query_validator.py - MINIMAL VERSION
# Let the AGENT be smart - validator only does basic filtering

import logging
import re
from typing import Dict

class QueryValidator:
    """
    MINIMAL validator - only filters out obvious non-data queries.
    The AGENT handles everything else including:
    - Determining if it's a greeting
    - Figuring out what information is missing
    - Asking for clarification
    
    This validator ONLY checks:
    1. Is this completely unrelated to weather/hydrology?
    2. Does this look like it might need data?
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Only filter out OBVIOUSLY non-weather topics
        self.NON_WEATHER_TOPICS = [
            'apple', 'banana', 'orange', 'fruit', 'food', 'recipe',
            'movie', 'film', 'tv show', 'actor', 'actress',
            'car', 'vehicle', 'automobile', 'truck',
            'phone', 'computer', 'laptop', 'software',
            'book', 'novel', 'author', 'poem',
            'song', 'music', 'album', 'artist', 'band',
            'game', 'video game', 'sport', 'soccer', 'football', 'basketball',
            'politics', 'politician', 'election', 'president',
            'stock', 'market', 'finance', 'investment'
        ]
        
        # Analysis method indicators (still needed for extreme queries)
        self.ANALYSIS_INDICATORS = [
            'top', 'hottest', 'coldest', 'warmest', 'wettest', 'driest',
            'most', 'highest', 'lowest', 'extreme', 'worst', 'best',
            'find regions', 'where are', 'which areas', 'significant'
        ]
        
        self.PIXEL_INDICATORS = ['pixel', 'grid', 'exact', 'coordinate', 'point']
        self.AREA_INDICATORS = ['rectangle', 'rectangular', 'area', 'box', 'region', 'zone', 'km', 'km²', 'km2', 'square km']
    
    def validate_query(self, user_query: str) -> Dict:
        """
        Minimal validation - just filter obvious non-weather queries.
        Everything else goes to the agent to handle intelligently.
        """
        query_lower = user_query.lower().strip()
        
        # Step 1: Is this obviously NOT about weather/hydrology?
        if self._is_obviously_non_weather(query_lower):
            # Still let agent handle it - agent can politely explain what it does
            return {
                'is_data_query': False,
                'is_analysis_query': False,
                'query_type': 'non_weather_topic',
                'is_valid': True,
                'should_execute_agent': True,
                'message': None
            }
        
        # Step 2: Check if it's an analysis query (needs method specification)
        is_analysis = self._is_analysis_query(query_lower)
        
        if is_analysis:
            # Validate analysis method
            extracted = self._extract_analysis_method(query_lower)
            
            if not extracted['has_method']:
                return {
                    'is_data_query': True,
                    'is_analysis_query': True,
                    'query_type': 'analysis_missing_method',
                    'is_valid': False,
                    'missing_analysis_method': True,
                    'extracted_params': extracted,
                    'message': self._generate_analysis_method_message(),
                    'should_execute_agent': False
                }
            
            if extracted['method'] == 'rectangular' and not extracted['area_size']:
                return {
                    'is_data_query': True,
                    'is_analysis_query': True,
                    'query_type': 'analysis_missing_area',
                    'is_valid': False,
                    'missing_area_size': True,
                    'extracted_params': extracted,
                    'message': self._generate_area_size_message(),
                    'should_execute_agent': False
                }
        
        # Step 3: Everything else - let agent handle it!
        # Agent will determine if it's:
        # - A greeting → respond naturally
        # - Missing info → ask for what's needed
        # - Complete query → execute
        return {
            'is_data_query': None,  # Agent determines
            'is_analysis_query': is_analysis,
            'query_type': 'let_agent_handle',
            'is_valid': True,
            'should_execute_agent': True,
            'extracted_params': extracted if is_analysis else None,
            'message': None
        }
    
    def _is_obviously_non_weather(self, query_lower: str) -> bool:
        """
        Only filter out OBVIOUSLY non-weather topics.
        This is very conservative - when in doubt, let the agent handle it.
        """
        # Check if query is asking about non-weather topics
        for topic in self.NON_WEATHER_TOPICS:
            if topic in query_lower:
                # Make sure it's not a place name that happens to contain the word
                # e.g., "Apple Valley, California" should not be filtered
                if not self._could_be_place_name(query_lower, topic):
                    self.logger.info(f"🚫 Filtering non-weather topic: {topic}")
                    return True
        
        return False
    
    def _could_be_place_name(self, query_lower: str, word: str) -> bool:
        """
        Check if the word might be part of a place name.
        Conservative - when in doubt, assume it could be a place.
        """
        # If there are location indicators nearby, might be a place
        location_words = ['in ', 'at ', 'near ', 'of ', 'for ', 'city', 'town', 'county', 'valley']
        return any(loc in query_lower for loc in location_words)
    
    def _is_analysis_query(self, query_lower: str) -> bool:
        """Check if this is asking to find regions/extremes"""
        return any(indicator in query_lower for indicator in self.ANALYSIS_INDICATORS)
    
    def _extract_analysis_method(self, query_lower: str) -> Dict:
        """Extract analysis method and area size"""
        extracted = {
            'has_method': False,
            'method': None,
            'area_size': None
        }
        
        # Check for analysis method
        has_pixel = any(keyword in query_lower for keyword in self.PIXEL_INDICATORS)
        has_area = any(keyword in query_lower for keyword in self.AREA_INDICATORS)
        
        if has_pixel:
            extracted['has_method'] = True
            extracted['method'] = 'pixel'
        elif has_area:
            extracted['has_method'] = True
            extracted['method'] = 'rectangular'
        
        # Extract area size if rectangular
        if extracted['method'] == 'rectangular':
            area_patterns = [
                r'(\d+)\s*km[²2]',
                r'(\d+)\s*square\s*km',
                r'area\s*of\s*(\d+)',
                r'(\d+)\s*km\s*area',
            ]
            
            for pattern in area_patterns:
                match = re.search(pattern, query_lower)
                if match:
                    extracted['area_size'] = int(match.group(1))
                    break
        
        return extracted
    
    def _generate_analysis_method_message(self) -> str:
        """Message asking for analysis method"""
        return (
            "I can find the extreme regions for you. "
            "How would you like me to analyze the regions?\n\n"
            "**Option 1: Pixel-based Analysis** 📍\n"
            "• Most precise - exact grid coordinates\n"
            "• Returns specific lat/lon points\n"
            "• Best for pinpoint accuracy\n\n"
            "**Option 2: Rectangular Area Analysis** 📦\n"
            "• Averaged over rectangular regions\n"
            "• You specify area size (e.g., 500 km²)\n"
            "• Better for regional patterns\n\n"
            "Please specify: **pixel-based** or **rectangular area-based**?"
        )
    
    def _generate_area_size_message(self) -> str:
        """Message asking for rectangular area size"""
        return (
            "Great! I'll use rectangular areas.\n\n"
            "**What size area would you like?**\n\n"
            "Examples:\n"
            "• Small regions: **100 km²** (10km × 10km)\n"
            "• Medium regions: **500 km²** (22km × 22km)\n"
            "• Large regions: **1000 km²** (32km × 32km)\n"
            "• Very large regions: **2500 km²** (50km × 50km)\n\n"
            "Just tell me: '500 km²' or 'use 1000 square km'"
        )


# Singleton instance
query_validator = QueryValidator()