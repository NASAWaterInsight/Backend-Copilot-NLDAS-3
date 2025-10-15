import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any  # NEW

try:
    from mem0 import Memory
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    Memory = None  # type: ignore

class MemoryManager:
    def __init__(self):
        self._error_count = 0  # NEW
        self.enabled = MEM0_AVAILABLE and bool(os.getenv("MEM0_SEARCH_SERVICE_NAME"))
        if not self.enabled:
            missing = []
            if not MEM0_AVAILABLE:
                missing.append("mem0ai_package")
            required_probe = ["MEM0_SEARCH_SERVICE_NAME","MEM0_SEARCH_API_KEY","AZURE_OPENAI_ENDPOINT",
                              "AZURE_OPENAI_API_KEY","MEM0_EMBED_MODEL","MEM0_CHAT_MODEL"]
            still_missing = [k for k in required_probe if not os.getenv(k)]
            missing.extend(still_missing)
            logging.info(f"MemoryManager: Mem0 not active (missing or empty: {', '.join(missing)})")
            logging.info("MemoryManager hint: export env vars in shell before running tests (local.settings.json is NOT auto-loaded by plain 'python').")
            return
        # Config from env
        service_name = os.getenv("MEM0_SEARCH_SERVICE_NAME")
        api_key = os.getenv("MEM0_SEARCH_API_KEY")
        embed_model = os.getenv("MEM0_EMBED_MODEL", "text-embedding-3-large")
        chat_model = os.getenv("MEM0_CHAT_MODEL", "gpt-4o")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        openai_key = os.getenv("AZURE_OPENAI_API_KEY")
        embed_dims = int(os.getenv("MEM0_EMBED_DIMS", "1536"))

        self.config = {
            "vector_store": {
                "provider": "azure_ai_search",
                "config": {
                    "service_name": service_name,
                    "api_key": api_key,
                    "collection_name": os.getenv("MEM0_COLLECTION", "nldas_memories"),
                    "embedding_model_dims": embed_dims,
                },
            },
            "embedder": {
                "provider": "azure_openai",
                "config": {
                    "model": embed_model,
                    "embedding_dims": embed_dims,
                    "azure_kwargs": {
                        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                        "azure_deployment": embed_model,
                        "azure_endpoint": endpoint,
                        "api_key": openai_key,
                    },
                },
            },
            "llm": {
                "provider": "azure_openai",
                "config": {
                    "model": chat_model,
                    "temperature": 0.0,
                    "max_tokens": 256,
                    "azure_kwargs": {
                        "azure_deployment": chat_model,
                        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
                        "azure_endpoint": endpoint,
                        "api_key": openai_key,
                    },
                },
            },
            "version": "v1.1",
        }
        try:
            self.memory = Memory.from_config(self.config)
            logging.info("MemoryManager: Mem0 initialized.")
        except Exception as e:
            logging.warning(f"MemoryManager initialization failed: {e}")
            self.enabled = False
            self.memory = None

    def _soft_fail(self, msg: str, exc: Exception):  # NEW
        self._error_count += 1
        logging.debug(f"MemoryManager soft-fail ({self._error_count}): {msg}: {exc}")
        if self._error_count >= 5:
            logging.warning("MemoryManager: too many errors; disabling memory.")
            self.enabled = False

    def add(self, text: str, user_id: str, meta: Optional[Dict[str, Any]] = None):
        if not self.enabled or not text:
            return
        try:
            self.memory.add(text, user_id=user_id, metadata=meta or {})
        except Exception as e:
            self._soft_fail("add", e)  # CHANGED

    def add_structured(
        self,
        user_id: str,
        variable: Optional[str],
        region: Optional[str],
        date_str: Optional[str],
        bounds: Optional[Dict[str, Any]],
        color_range: Optional[Dict[str, Any]]
    ):
        parts = []
        if variable: parts.append(f"variable={variable}")
        if region: parts.append(f"region={region}")
        if date_str: parts.append(f"date_scope={date_str}")
        if bounds and all(k in bounds for k in ("north","south","east","west")):
            parts.append(f"bounds={bounds['south']},{bounds['west']}–{bounds['north']},{bounds['east']}")
        if color_range and all(k in color_range for k in ("min","max")):
            parts.append(f"color_range={color_range['min']}..{color_range['max']}")
        if not parts:
            return
        text = " | ".join(parts)
        self.add(f"[MAP_CONTEXT] {text}", user_id, {"type": "map_context", "ts": datetime.utcnow().isoformat()})

    def search(self, query: str, user_id: str, limit: int = 5):
        if not self.enabled:
            return []
        try:
            res = self.memory.search(query, user_id=user_id, limit=limit)
            return res.get("results", [])
        except Exception as e:
            self._soft_fail("search", e)  # CHANGED
            return []

    def recent_context(self, user_id: str, limit: int = 5):
        # Query broad context
        return self.search("recent map context", user_id, limit=limit)

    def validate_env(self) -> Dict[str, Any]:  # NEW / UPDATED
        required = ["MEM0_SEARCH_SERVICE_NAME","MEM0_SEARCH_API_KEY","AZURE_OPENAI_ENDPOINT",
                    "AZURE_OPENAI_API_KEY","MEM0_EMBED_MODEL","MEM0_CHAT_MODEL","MEM0_EMBED_DIMS","AZURE_OPENAI_API_VERSION"]
        report = {k: bool(os.getenv(k)) for k in required}
        report["enabled"] = self.enabled
        report["errors"] = self._error_count
        report["missing"] = [k for k,v in report.items() if k not in ("enabled","errors","missing") and not v]
        return report

    def debug_status(self):  # NEW
        """Return a redacted diagnostic dict for logs or tests."""
        keys = ["MEM0_SEARCH_SERVICE_NAME","MEM0_SEARCH_API_KEY","AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_API_KEY","MEM0_EMBED_MODEL","MEM0_CHAT_MODEL","MEM0_EMBED_DIMS","AZURE_OPENAI_API_VERSION"]
        diag = {}
        for k in keys:
            v = os.getenv(k)
            if not v:
                diag[k] = "<missing>"
            elif "KEY" in k or "API" in k:
                diag[k] = f"<set:{len(v)}chars>"
            else:
                diag[k] = v
        diag["enabled"] = self.enabled
        diag["errors"] = self._error_count
        return diag

memory_manager = MemoryManager()
