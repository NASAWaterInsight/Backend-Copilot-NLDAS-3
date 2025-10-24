# agents/query_validator.py - Minimal validator with proper attributes
import logging
import re
from typing import Dict

class QueryValidator:
    """
    Minimal validator - only checks query type and analysis method.
    Lets the agent handle region detection, boundary finding, and validation.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Data query indicators
        self.DATA_QUERY_INDICATORS = [
            'show', 'map', 'plot', 'visualize', 'display', 'chart', 'graph',
            'what is', 'what was', 'tell me', 'how much', 'calculate',
            'average', 'mean', 'max', 'min', 'trend', 'compare', 'analyze',
            'find', 'get', 'give me', 'i want', 'i need'
        ]
        
        # Analysis query indicators - queries that find regions/extremes
        self.ANALYSIS_INDICATORS = [
            'top', 'hottest', 'coldest', 'warmest', 'wettest', 'driest',
            'most', 'highest', 'lowest', 'extreme', 'worst', 'best',
            'find regions', 'where are', 'which areas', 'significant'
        ]
        
        # Weather/hydrology domain keywords (broad check)
        self.DOMAIN_KEYWORDS = [
            'temperature', 'temp', 'precipitation', 'rain', 'drought', 'spi',
            'humidity', 'moisture', 'wind', 'pressure', 'weather', 'climate',
            'hot', 'cold', 'warm', 'wet', 'dry'
        ]
        
        # Analysis method indicators
        self.PIXEL_INDICATORS = ['pixel', 'grid', 'exact', 'coordinate', 'point']
        self.AREA_INDICATORS = ['rectangle', 'rectangular', 'area', 'box', 'region', 'zone', 'km', 'km²', 'km2', 'square km']
    
    def validate_query(self, user_query: str) -> Dict:
        """
        Minimal validation - only check query type and analysis method.
        Let agent handle everything else (regions, dates, boundaries, etc.)
        """
        query_lower = user_query.lower().strip()
        
        # Step 1: Is this general conversation? (greetings, thanks, etc.)
        if self._is_general_conversation(query_lower):
            return {
                'is_data_query': False,
                'is_analysis_query': False,
                'is_valid': True,
                'should_execute_agent': True
            }
        
        # Step 2: Is this a data query?
        is_data_query = self._is_data_query(query_lower)
        
        if not is_data_query:
            # Not a data query, but not general conversation either
            # Let agent handle it (might be capability question, etc.)
            return {
                'is_data_query': False,
                'is_analysis_query': False,
                'is_valid': True,
                'should_execute_agent': True
            }
        
        # Step 3: Is this an analysis query (finding extremes)?
        is_analysis_query = self._is_analysis_query(query_lower)
        
        if not is_analysis_query:
            # Regular data query (specific location) - agent handles everything
            return {
                'is_data_query': True,
                'is_analysis_query': False,
                'is_valid': True,
                'should_execute_agent': True
            }
        
        # Step 4: For analysis queries, check if analysis method is specified
        extracted = self._extract_analysis_method(query_lower)
        
        if not extracted['has_method']:
            # Missing analysis method - ask user
            return {
                'is_data_query': True,
                'is_analysis_query': True,
                'is_valid': False,
                'missing_analysis_method': True,
                'extracted_params': extracted,
                'message': self._generate_analysis_method_message(),
                'should_execute_agent': False
            }
        
        if extracted['method'] == 'rectangular' and not extracted['area_size']:
            # Has rectangular method but missing size
            return {
                'is_data_query': True,
                'is_analysis_query': True,
                'is_valid': False,
                'missing_area_size': True,
                'extracted_params': extracted,
                'message': self._generate_area_size_message(),
                'should_execute_agent': False
            }
        
        # All good - execute analysis
        return {
            'is_data_query': True,
            'is_analysis_query': True,
            'is_valid': True,
            'extracted_params': extracted,
            'should_execute_agent': True
        }
    
    def _is_general_conversation(self, query_lower: str) -> bool:
        """Quick check for greetings and casual chat"""
        greetings = [
            'hello', 'hi ', 'hey ', 'good morning', 'good afternoon', 'good evening',
            'thanks', 'thank you', "how are you", "what's up", 'bye', 'goodbye'
        ]
        return any(g in query_lower for g in greetings) and len(query_lower.split()) < 10
    
    def _is_data_query(self, query_lower: str) -> bool:
        """
        Check if this is asking for data/analysis.
        Only checks for action indicators + domain keywords.
        Does NOT validate if specific parameters are present.
        """
        # Special case: "show me the map" with no other context
        if query_lower in ['show me the map', 'show the map', 'show map', 'show me map']:
            return False  # Too vague
        
        # Special case: very short queries with "map"
        if 'map' in query_lower and len(query_lower.split()) <= 4:
            return False
        
        # Check for data query indicators
        has_indicator = any(indicator in query_lower for indicator in self.DATA_QUERY_INDICATORS)
        
        if not has_indicator:
            return False
        
        # Check if it mentions our domain
        has_domain = any(keyword in query_lower for keyword in self.DOMAIN_KEYWORDS)
        
        return has_domain
    
    def _is_analysis_query(self, query_lower: str) -> bool:
        """Check if this is asking to find regions/extremes"""
        return any(indicator in query_lower for indicator in self.ANALYSIS_INDICATORS)
    
    def _extract_analysis_method(self, query_lower: str) -> Dict:
        """Extract only analysis method and area size - nothing else"""
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