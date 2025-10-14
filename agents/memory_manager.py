import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    Memory = None
    logging.warning("⚠️ Mem0 not available — memory features disabled")


class MemoryManager:
    """Enhanced Mem0 wrapper with graph memory and multimodal support."""

    def __init__(self):
        self.enabled = False
        self.memory = None

        if MEM0_AVAILABLE:
            self._initialize_mem0()

    def _initialize_mem0(self):
        """Initialize Mem0 with Azure AI Search, OpenAI, and Graph Memory support"""
        try:
            # Enhanced configuration based on Microsoft Semantic Kernel + Mem0 articles
            config = {
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
                            "api_version": "2024-12-01-preview",
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
                            "api_version": "2025-01-01-preview",
                            "azure_endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),
                            "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
                        },
                    },
                },
                # OPTIONAL: Enable graph memory for relationship tracking
                # Uncomment if you have Neo4j set up
                # "graph_store": {
                #     "provider": "neo4j",
                #     "config": {
                #         "url": os.getenv("NEO4J_URL", "neo4j+s://xxx"),
                #         "username": os.getenv("NEO4J_USERNAME", "neo4j"),
                #         "password": os.getenv("NEO4J_PASSWORD"),
                #     }
                # },
                # Custom prompt to filter what gets stored
                "custom_prompt": """
                Extract only weather analysis context, user preferences, and location/variable/date patterns.
                Ignore casual greetings and general knowledge queries.
                
                Examples:
                Input: "Hello, how are you?"
                Output: {"facts": []}
                
                Input: "Show me temperature map for Florida on March 15, 2023"
                Output: {"facts": [
                    "User requested temperature analysis",
                    "Location: Florida",
                    "Date: March 15, 2023",
                    "Variable: temperature"
                ]}
                
                Input: "I prefer seeing precipitation as mm rather than inches"
                Output: {"facts": ["User prefers precipitation in mm units"]}
                """,
                "version": "v1.1",
            }
            
            # Validate required configuration
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
        Uses semantic search without a specific query to get most recent relevant memories.
        """
        if not self.enabled:
            return []

        try:
            # FIXED: Search with empty query to get recent memories
            results = self.memory.search(
                query="",
                user_id=user_id,
                limit=limit
            )
            
            context = []
            memories = results.get('results', []) if isinstance(results, dict) else results
            
            for result in memories:
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