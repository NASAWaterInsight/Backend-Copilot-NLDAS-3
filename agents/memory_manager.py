import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# -----------------------------------------------------------------------------
# Try Importing Mem0
# -----------------------------------------------------------------------------
try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    Memory = None
    logging.warning("⚠️ Mem0 not available — memory features disabled")


# -----------------------------------------------------------------------------
# MemoryManager Class
# -----------------------------------------------------------------------------
class MemoryManager:
    """Wrapper for Mem0 memory system integrated with Azure OpenAI + Azure AI Search."""

    def __init__(self):
        self.enabled = False
        self.memory = None

        if MEM0_AVAILABLE:
            self._initialize_mem0()

    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------
    def _initialize_mem0(self):
        """Initialize Mem0 with Azure AI Search and OpenAI configuration"""
        try:
            # FIXED: Configuration based on Microsoft Azure AI Foundry blog post format
            config = {
                "vector_store": {
                    "provider": "azure_ai_search",
                    "config": {
                        "service_name": os.getenv("MEM0_SERVICE_NAME"),
                        "api_key": os.getenv("MEM0_API_KEY"),
                        "collection_name": os.getenv("MEM0_COLLECTION_NAME", "nldas_memories"),
                        "embedding_model_dims": int(os.getenv("MEM0_EMBED_DIMS", "1536")),
                        "compression_type": "binary",
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
                "llm": {
                    "provider": "azure_openai",
                    "config": {
                        "model": os.getenv("MEM0_CHAT_MODEL", "gpt-4o"),
                        "temperature": 0.1,
                        "max_tokens": 2000,
                        "azure_kwargs": {
                            "azure_deployment": os.getenv("MEM0_CHAT_MODEL", "gpt-4o"),
                            "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                            "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                            "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                        },
                    },
                },
                "version": "v1.1",
            }
            
            # Validate required configuration - UPDATED variable names
            required_vars = [
                "MEM0_SERVICE_NAME",
                "MEM0_API_KEY",
                "AZURE_OPENAI_API_KEY",
                "AZURE_OPENAI_ENDPOINT"
            ]
            
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            
            if missing_vars:
                logging.warning(f"Missing Mem0 configuration: {missing_vars}")
                return
            
            # Initialize Mem0
            self.memory = Memory.from_config(config)
            self.enabled = True
            
            logging.info("✅ Mem0 Memory Manager initialized successfully")
            logging.info(f"   Search Service: {os.getenv('MEM0_SERVICE_NAME')}")
            logging.info(f"   Collection Name: {os.getenv('MEM0_COLLECTION_NAME', 'nldas_memories')}")
            
        except Exception as e:
            logging.error(f"❌ Failed to initialize Mem0: {e}")
            self.enabled = False

    # -------------------------------------------------------------------------
    # Core Functions
    # -------------------------------------------------------------------------
    def add(self, text: str, user_id: str, meta: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Add a memory for a specific user."""
        if not self.enabled:
            logging.warning("⚠️ Memory manager not enabled — skipping add()")
            return None

        try:
            metadata = {"timestamp": datetime.now().isoformat(), "type": "conversation"}
            if meta:
                metadata.update(meta)

            result = self.memory.add(messages=text, user_id=user_id, metadata=metadata)
            memory_id = result.get("id") if isinstance(result, dict) else str(result)

            logging.info(f"✅ Added memory for user {user_id[:8]}…: {text[:50]}…")
            return memory_id

        except Exception as e:
            logging.error(f"❌ Failed to add memory: {e}")
            return None

    # -------------------------------------------------------------------------
    def search(self, query: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search memories for a specific user."""
        if not self.enabled:
            return []

        try:
            results = self.memory.search(query=query, user_id=user_id, limit=limit)
            if results:
                logging.info(f"🔍 Found {len(results)} memories for {user_id[:8]}… query: {query[:30]}…")
            else:
                logging.info(f"🔍 No memories found for {user_id[:8]}… query: {query[:30]}…")
            return results or []

        except Exception as e:
            logging.error(f"❌ Failed to search memories: {e}")
            return []

    # -------------------------------------------------------------------------
    def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all memories for a user (GDPR support)."""
        if not self.enabled:
            return []

        try:
            results = self.memory.get_all(user_id=user_id)
            logging.info(f"📋 Retrieved {len(results)} total memories for {user_id[:8]}…")
            return results

        except Exception as e:
            logging.error(f"❌ Failed to get all memories: {e}")
            return []

    # -------------------------------------------------------------------------
    def delete(self, memory_id: str) -> bool:
        """Delete a specific memory (GDPR support)."""
        if not self.enabled:
            return False

        try:
            self.memory.delete(memory_id)
            logging.info(f"🗑️ Deleted memory: {memory_id}")
            return True

        except Exception as e:
            logging.error(f"❌ Failed to delete memory {memory_id}: {e}")
            return False

    # -------------------------------------------------------------------------
    def recent_context(self, user_id: str, limit: int = 3) -> List[str]:
        """Get recent conversation context for a user."""
        if not self.enabled:
            return []

        try:
            results = self.memory.search(query="", user_id=user_id, limit=limit)
            context = []
            for result in results:
                if isinstance(result, dict):
                    context.append(result.get("memory") or result.get("text", ""))
                else:
                    context.append(str(result))
            return [c for c in context if c]

        except Exception as e:
            logging.error(f"❌ Failed to get recent context: {e}")
            return []

    # -------------------------------------------------------------------------
    def add_structured(
        self,
        user_id: str,
        variable: str,
        region: str,
        date_str: str,
        bounds: Dict[str, Any],
        color_range: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Add structured memory for geospatial / analysis context."""
        memory_text = f"User analyzed {variable} for {region} in {date_str}"
        metadata = {
            "type": "analysis",
            "variable": variable,
            "region": region.lower(),
            "date_str": date_str,
            "bounds": bounds,
        }
        if color_range:
            metadata["color_range"] = color_range
        return self.add(memory_text, user_id, metadata)


# -----------------------------------------------------------------------------
# Singleton Instance
# -----------------------------------------------------------------------------
memory_manager = MemoryManager()
