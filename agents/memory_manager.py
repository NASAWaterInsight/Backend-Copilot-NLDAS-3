import os
import json
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
import re

# ✅ CRITICAL: Block OpenAI API key BEFORE any imports
if "OPENAI_API_KEY" in os.environ:
    logging.warning(f"⚠️ Found OPENAI_API_KEY in environment - REMOVING IT")
    del os.environ["OPENAI_API_KEY"]

if "OPENAI_BASE_URL" in os.environ:
    logging.warning(f"⚠️ Found OPENAI_BASE_URL in environment - REMOVING IT")
    del os.environ["OPENAI_BASE_URL"]

# Load settings AFTER blocking OpenAI keys
def load_local_settings():
    """Load environment variables from local.settings.json for local development"""
    settings_path = os.path.join(os.path.dirname(__file__), "../local.settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                values = settings.get("Values", {})
                for key, value in values.items():
                    # ✅ SKIP OpenAI keys entirely
                    if key in ["OPENAI_API_KEY", "OPENAI_BASE_URL"]:
                        logging.warning(f"⚠️ Skipping {key} from local.settings.json")
                        continue
                    
                    if key.startswith(("MEM0_", "AZURE_OPENAI_")):
                        os.environ[key] = value
                        logging.info(f"✅ Loaded {key} from local.settings.json")
        except Exception as e:
            logging.warning(f"⚠️ Could not load local.settings.json: {e}")

# Load settings on import
load_local_settings()

# Configure logging ONCE
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ✅ DOUBLE-CHECK: Remove OpenAI keys again after loading settings
if "OPENAI_API_KEY" in os.environ:
    logging.error(f"⚠️ OPENAI_API_KEY still present after load_local_settings - FORCING REMOVAL")
    del os.environ["OPENAI_API_KEY"]

if "OPENAI_BASE_URL" in os.environ:
    logging.error(f"⚠️ OPENAI_BASE_URL still present after load_local_settings - FORCING REMOVAL")
    del os.environ["OPENAI_BASE_URL"]

# Now import Mem0 ONCE
try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
    logging.info("✅ Mem0 imported successfully")
except ImportError as e:
    MEM0_AVAILABLE = False
    Memory = None
    logging.warning(f"⚠️ Mem0 not available — memory features disabled: {e}")




class MemoryManager:
    """Enhanced Mem0 wrapper with graph memory and multimodal support."""

    def __init__(self):
        self.enabled = False
        self.memory = None

        if MEM0_AVAILABLE:
            self._initialize_mem0()

    # In memory_manager.py, update _initialize_mem0:

    def _initialize_mem0(self):
        """Initialize Mem0 with Azure AI Search, Azure OpenAI LLM, and Graph Memory support"""
        try:
            # ✅ ADD DETAILED LOGGING
            logging.info("=" * 60)
            logging.info("🔧 Initializing Mem0 Memory Manager...")
            logging.info("=" * 60)
            
            # Check each required variable
            required_vars = {
                "MEM0_SERVICE_NAME": os.getenv("MEM0_SERVICE_NAME"),
                "MEM0_API_KEY": os.getenv("MEM0_API_KEY"),
                "AZURE_OPENAI_API_KEY": os.getenv("AZURE_OPENAI_API_KEY"),
                "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT"),
                "AZURE_OPENAI_MODEL": os.getenv("AZURE_OPENAI_MODEL")
            }
            
            # Log each variable (safely)
            for var_name, var_value in required_vars.items():
                if var_value:
                    # Show first/last 4 chars for keys
                    if "KEY" in var_name or "TOKEN" in var_name:
                        safe_value = f"{var_value[:4]}...{var_value[-4:]}" if len(var_value) > 8 else "***"
                    else:
                        safe_value = var_value
                    logging.info(f"✅ {var_name}: {safe_value}")
                else:
                    logging.error(f"❌ {var_name}: NOT SET")
            
            # Check for missing vars
            missing_vars = [var for var, val in required_vars.items() if not val]
            
            if missing_vars:
                logging.error(f"❌ Missing Mem0 configuration: {missing_vars}")
                logging.error("❌ Memory manager will be DISABLED")
                return
            
            # ✅ COMPLETE CONFIG WITH LLM
            config = {
                "llm": {
                    "provider": "azure_openai",
                    "config": {
                        "model": os.getenv("AZURE_OPENAI_MODEL", "gpt-4o"),
                        "temperature": 0.1,
                        "max_tokens": 1000,
                        "azure_kwargs": {
                            "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                            "azure_deployment": os.getenv("AZURE_OPENAI_MODEL", "gpt-4o"),
                            "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                            "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                        }
                    }
                },
                "vector_store": {
                    "provider": "azure_ai_search",
                    "config": {
                        "service_name": os.getenv("MEM0_SERVICE_NAME"),
                        "api_key": os.getenv("MEM0_API_KEY"),
                        "collection_name": os.getenv("MEM0_COLLECTION_NAME", "nldas_memories"),
                        "embedding_model_dims": int(os.getenv("MEM0_EMBED_DIMS", "1536")),
                    },
                },
                "embedder": {
                    "provider": "azure_openai",
                    "config": {
                        "model": os.getenv("MEM0_EMBED_MODEL", "text-embedding-ada-002"),
                        "embedding_dims": int(os.getenv("MEM0_EMBED_DIMS", "1536")),
                        "azure_kwargs": {
                            "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                            "azure_deployment": os.getenv("MEM0_EMBED_MODEL", "text-embedding-ada-002"),
                            "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                            "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                        },
                    },
                },
            }
            
            logging.info("🔄 Initializing Mem0 with config...")
            
            # Initialize Mem0
            self.memory = Memory.from_config(config)
            self.enabled = True
            
            logging.info("=" * 60)
            logging.info("✅ Mem0 Memory Manager initialized successfully")
            logging.info(f"   Search Service: {os.getenv('MEM0_SERVICE_NAME')}")
            logging.info(f"   Collection: {os.getenv('MEM0_COLLECTION_NAME', 'nldas_memories')}")
            logging.info(f"   Embedding Model: {os.getenv('MEM0_EMBED_MODEL', 'text-embedding-ada-002')}")
            logging.info(f"   LLM Model: {os.getenv('AZURE_OPENAI_MODEL', 'gpt-4o')}")
            logging.info("=" * 60)
            
        except Exception as e:
            logging.error("=" * 60)
            logging.error(f"❌ Failed to initialize Mem0: {e}")
            logging.error(f"❌ Traceback: {traceback.format_exc()}")
            logging.error("=" * 60)
            self.enabled = False

    def add(self, text: str, user_id: str, meta: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Add a memory with contextual metadata.
        Uses Mem0's intelligent extraction to store only relevant information.
        """
        if not self.enabled:
            logging.warning("⚠️ Memory manager not enabled — skipping add()")
            return None

        try:
            # Structure as conversation message for better extraction
            messages = [
                {"role": "user", "content": text}
            ]
            
            metadata = {
                "timestamp": datetime.now().isoformat(),
                "type": meta.get("type", "conversation") if meta else "conversation"
            }
            if meta:
                metadata.update({k: v for k, v in meta.items() if k != "type"})

            # FIXED: Remove version parameter for compatibility
            result = self.memory.add(
                messages=messages,
                user_id=user_id,
                metadata=metadata
            )
            
            # Handle response format
            if isinstance(result, list) and len(result) > 0:
                memory_id = result[0].get("id") if isinstance(result[0], dict) else str(result[0])
                logging.info(f"✅ Added memory for user {user_id[:8]}…: {text[:50]}…")
                return memory_id
            elif isinstance(result, dict):
                memory_id = result.get("id", str(result))
                logging.info(f"✅ Added memory for user {user_id[:8]}…: {text[:50]}…")
                return memory_id
            else:
                logging.warning(f"⚠️ Unexpected add() response format: {type(result)}")
                return str(result) if result else None

        except Exception as e:
            logging.error(f"❌ Failed to add memory: {e}")
            return None

    def search(self, query: str, user_id: str, limit: int = 5, enable_graph: bool = False) -> List[Dict[str, Any]]:
        """
        Search memories with semantic similarity and optional graph relationships.
        Returns memories sorted by relevance score.
        """
        if not self.enabled:
            return []

        try:
            # FIXED: Use basic search parameters without version/output_format
            search_params = {
                "query": query,
                "user_id": user_id,
                "limit": limit
            }
            
            results = self.memory.search(**search_params)
            
            # Handle different response formats
            if isinstance(results, dict):
                memories = results.get('results', [])
                relations = results.get('relations', [])
                
                if relations:
                    logging.info(f"🔗 Found {len(relations)} relationships for {user_id[:8]}…")
                
                if memories:
                    logging.info(f"🔍 Found {len(memories)} memories for {user_id[:8]}… query: {query[:30]}…")
                    # Log relevance scores
                    for mem in memories[:3]:  # Log top 3
                        score = mem.get('score', 0)
                        content = mem.get('memory', '')[:50]
                        logging.info(f"   Score: {score:.3f} - {content}...")
                else:
                    logging.info(f"🔍 No memories found for {user_id[:8]}… query: {query[:30]}…")
                
                return memories
            elif isinstance(results, list):
                if results:
                    logging.info(f"🔍 Found {len(results)} memories for {user_id[:8]}… query: {query[:30]}…")
                return results
            else:
                logging.warning(f"⚠️ Unexpected search response format: {type(results)}")
                return []

        except Exception as e:
            logging.error(f"❌ Failed to search memories: {e}")
            return []

    def add_with_image(self, text: str, image_url: str, user_id: str, meta: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Add multimodal memory with image context.
        Mem0 will extract information from both text and image.
        """
        if not self.enabled:
            return None

        try:
            # Structure multimodal message
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    }
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
            
            metadata = {
                "timestamp": datetime.now().isoformat(),
                "type": "multimodal",
                "has_image": True
            }
            if meta:
                metadata.update(meta)

            # FIXED: Remove version and enable_vision parameters for compatibility
            result = self.memory.add(
                messages=messages,
                user_id=user_id,
                metadata=metadata
            )
            
            memory_id = self._extract_memory_id(result)
            logging.info(f"✅ Added multimodal memory for user {user_id[:8]}… with image")
            return memory_id

        except Exception as e:
            logging.error(f"❌ Failed to add multimodal memory: {e}")
            return None

    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all memories for a user (GDPR compliance)."""
        if not self.enabled:
            return []

        try:
            results = self.memory.get_all(user_id=user_id)
            
            if isinstance(results, dict):
                memories = results.get('results', [])
                logging.info(f"📋 Retrieved {len(memories)} total memories for {user_id[:8]}…")
                return memories
            elif isinstance(results, list):
                logging.info(f"📋 Retrieved {len(results)} total memories for {user_id[:8]}…")
                return results
            else:
                return []

        except Exception as e:
            logging.error(f"❌ Failed to get all memories: {e}")
            return []

    def delete(self, memory_id: str) -> bool:
        """Delete a specific memory (GDPR Right to Erasure)."""
        if not self.enabled:
            return False

        try:
            self.memory.delete(memory_id)
            logging.info(f"🗑️ Deleted memory: {memory_id}")
            return True

        except Exception as e:
            logging.error(f"❌ Failed to delete memory {memory_id}: {e}")
            return False

    def delete_all_user_memories(self, user_id: str) -> bool:
        """Delete all memories for a user (GDPR compliance)."""
        if not self.enabled:
            return False

        try:
            self.memory.delete_all(user_id=user_id)
            logging.info(f"🗑️ Deleted all memories for user: {user_id[:8]}…")
            return True

        except Exception as e:
            logging.error(f"❌ Failed to delete user memories: {e}")
            return False

    def get_history(self, memory_id: str) -> List[Dict[str, Any]]:
        """Get version history of a specific memory."""
        if not self.enabled:
            return []

        try:
            history = self.memory.history(memory_id=memory_id)
            logging.info(f"📜 Retrieved history for memory {memory_id}: {len(history)} versions")
            return history

        except Exception as e:
            logging.error(f"❌ Failed to get memory history: {e}")
            return []

    def recent_context(self, user_id: str, limit: int = 3) -> List[str]:
        """
        Get recent conversation context for a user.
        FIXED: Use get_all instead of search with empty query
        """
        if not self.enabled:
            return []

        try:
            # FIXED: Use get_all to avoid API issues with empty search
            all_memories = self.memory.get_all(user_id=user_id)
            
            context = []
            memories = all_memories.get('results', []) if isinstance(all_memories, dict) else all_memories
            
            # Get most recent memories (limited by limit parameter)
            recent_memories = memories[:limit] if len(memories) > limit else memories
            
            for result in recent_memories:
                if isinstance(result, dict):
                    memory_text = result.get("memory") or result.get("text", "")
                    if memory_text:
                        context.append(memory_text)
                else:
                    context.append(str(result))
            
            return [c for c in context if c]

        except Exception as e:
            logging.error(f"❌ Failed to get recent context: {e}")
            return []
        
    def add_flash_drought_analysis(
        self,
        user_id: str,
        region: str,
        start_period: str,
        end_period: str,
        result_url: str,
        percentage_affected: float
    ) -> Optional[str]:
        """Add flash drought analysis to memory"""
        memory_text = f"Flash drought analysis for {region} from {start_period} to {end_period}. {percentage_affected:.1f}% of area affected."
        
        metadata = {
            "type": "flash_drought_analysis",
            "region": region.lower(),
            "start_period": start_period,
            "end_period": end_period,
            "percentage_affected": percentage_affected,
            "result_url": result_url,
            "analysis_pattern": "flash_drought"
        }
        
        return self.add(memory_text, user_id, metadata)

    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Extract user preferences from memory"""
        if not self.enabled:
            return {}
        
        try:
            prefs = self.search("preference prefer color visualization", user_id, limit=5)
            
            extracted_prefs = {
                "regions_of_interest": [],
                "preferred_variables": [],
                "visualization_preferences": []
            }
            
            for memory in prefs:
                metadata = memory.get("metadata", {})
                if metadata.get("type") == "analysis":
                    region = metadata.get("region")
                    if region and region not in extracted_prefs["regions_of_interest"]:
                        extracted_prefs["regions_of_interest"].append(region)
            
            return extracted_prefs
        except Exception as e:
            logging.error(f"❌ Failed to extract preferences: {e}")
            return {}

    def add_drought_recovery_analysis(
    self,
    user_id: str,
    region: str,
    recovery_period: str,
    recovery_percentage: float,
    result_url: str
) -> Optional[str]:
        """Add drought recovery analysis to memory"""
        memory_text = f"Drought recovery analysis for {region} during {recovery_period}. {recovery_percentage:.1f}% of area recovered from drought conditions."
        
        metadata = {
            "type": "drought_recovery_analysis", 
            "region": region.lower(),
            "recovery_period": recovery_period,
            "recovery_percentage": recovery_percentage,
            "result_url": result_url,
            "analysis_pattern": "drought_recovery"
        }
        
        return self.add(memory_text, user_id, metadata)
    
    def search_by_pattern(self, user_id: str, pattern_type: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search memories by analysis pattern (flash_drought, drought_recovery, etc.)"""
        if not self.enabled:
            return []
            
        try:
            # Search for specific analysis patterns
            pattern_queries = {
                "flash_drought": "flash drought rapid deterioration areas SPI dropped",
                "drought_recovery": "drought recovery improvement areas recovered",
                "temperature_analysis": "temperature maps thermal analysis",
                "precipitation_analysis": "precipitation rainfall maps",
                "comparative_analysis": "compare comparison between years"
            }
            
            query = pattern_queries.get(pattern_type, pattern_type)
            return self.search(query, user_id, limit)
            
        except Exception as e:
            logging.error(f"❌ Failed pattern search: {e}")
            return []
        
    def extract_query_context(self, user_query: str, user_id: str) -> Dict[str, Any]:
        """Extract context from user query and previous memories"""
        if not self.enabled:
            return {}
        
        try:
            context = {
                "variables": [],
                "regions": [],
                "time_periods": [],
                "analysis_types": [],
                "implicit_references": False
            }
            
            query_lower = user_query.lower()
            
            # Check for implicit references
            implicit_words = ["same", "this", "that", "similar", "compare", "again"]
            if any(word in query_lower for word in implicit_words):
                context["implicit_references"] = True
                
                # Get recent context to resolve references
                recent_memories = self.recent_context(user_id, limit=3)
                if recent_memories:
                    context["recent_context"] = recent_memories
            
            # Extract variable mentions
            variables = ["temperature", "precipitation", "drought", "spi", "humidity"]
            for var in variables:
                if var in query_lower:
                    context["variables"].append(var)
            
            # Extract region mentions  
            regions = ["florida", "california", "texas", "maryland", "great plains"]
            for region in regions:
                if region in query_lower:
                    context["regions"].append(region)
            
            # Extract time period mentions
            import re
            year_match = re.search(r'(20\d{2})', user_query)
            if year_match:
                context["time_periods"].append(year_match.group(1))
            
            return context
            
        except Exception as e:
            logging.error(f"❌ Failed to extract query context: {e}")
            return {}

    def add_structured_analysis(
        self,
        user_id: str,
        variable: str,
        region: str,
        date_str: str,
        bounds: Dict[str, Any],
        result_url: Optional[str] = None,
        color_range: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Add structured memory for weather analysis context.
        This creates a rich, queryable memory of the analysis performed.
        """
        # Create descriptive memory text
        memory_text = f"Analyzed {variable} data for {region} on {date_str}"
        if result_url:
            memory_text += f". Generated visualization: {result_url}"
        
        metadata = {
            "type": "analysis",
            "variable": variable.lower(),
            "region": region.lower(),
            "date_str": date_str,
            "bounds": bounds,
        }
        
        if color_range:
            metadata["color_range"] = color_range
        
        if result_url:
            metadata["result_url"] = result_url
        
        return self.add(memory_text, user_id, metadata)

    def _extract_memory_id(self, result: Any) -> Optional[str]:
        """Helper to extract memory ID from various response formats."""
        if isinstance(result, list) and len(result) > 0:
            return result[0].get("id") if isinstance(result[0], dict) else str(result[0])
        elif isinstance(result, dict):
            return result.get("id", str(result))
        else:
            return str(result) if result else None
    
    


# Singleton instance
memory_manager = MemoryManager()