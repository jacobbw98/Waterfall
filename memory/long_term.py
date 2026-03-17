"""
Long-Term Memory — powered by MemOS.

Provides cross-session persistent memory via MemOS REST API.
Supports both cloud (hosted) and self-hosted (Docker) backends.
Stores task summaries, user preferences, and learned facts that
persist across agent restarts.
"""
import os
import json
import uuid
from typing import Optional, List, Dict, Any

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class LongTermMemory:
    """
    Cross-session persistent memory using MemOS REST API.
    
    Automatically stores task summaries and learned facts, allowing
    the agent to recall relevant context from previous sessions.
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        user_id: Optional[str] = None,
        cube_id: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        """
        Initialize long-term memory.
        
        Args:
            base_url: MemOS server URL (env: MEMOS_URL, default: http://localhost:8000)
            user_id: MemOS user ID (env: MEMOS_USER_ID, auto-generated if not set)  
            cube_id: MemOS memory cube ID (env: MEMOS_CUBE_ID, auto-generated if not set)
            api_key: Optional API key for cloud mode (env: MEMOS_API_KEY)
        """
        self.base_url = (base_url or os.environ.get("MEMOS_URL", "http://localhost:8000")).rstrip("/")
        self.user_id = user_id or os.environ.get("MEMOS_USER_ID", str(uuid.uuid4()))
        self.cube_id = cube_id or os.environ.get("MEMOS_CUBE_ID", str(uuid.uuid4()))
        self.api_key = api_key or os.environ.get("MEMOS_API_KEY")
        
        self._available = REQUESTS_AVAILABLE
        self._connected = False
        
        if not self._available:
            print("[LongTermMemory] WARNING: 'requests' library not installed.")
    
    @property
    def available(self) -> bool:
        return self._available
    
    def _headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    def check_connection(self) -> str:
        """Test if MemOS server is reachable."""
        if not self._available:
            return "Long-term memory unavailable: 'requests' library not installed."
        
        try:
            resp = requests.get(f"{self.base_url}/", timeout=5)
            self._connected = resp.status_code < 500
            if self._connected:
                return f"MemOS connected at {self.base_url}"
            return f"MemOS returned status {resp.status_code}"
        except requests.ConnectionError:
            self._connected = False
            return (f"Cannot connect to MemOS at {self.base_url}. "
                    f"Start it with: cd vendor/MemOS/docker && docker-compose up -d")
        except Exception as e:
            self._connected = False
            return f"MemOS connection error: {e}"
    
    def store(self, content: str, role: str = "assistant") -> str:
        """
        Store a memory (message, fact, task summary) in MemOS.
        
        Args:
            content: The text to remember
            role: Message role (user/assistant)
            
        Returns:
            Confirmation or error message
        """
        if not self._available:
            return "Long-term memory unavailable: 'requests' not installed."
        
        data = {
            "user_id": self.user_id,
            "mem_cube_id": self.cube_id,
            "messages": [
                {"role": role, "content": content}
            ],
            "async_mode": "sync"
        }
        
        try:
            resp = requests.post(
                f"{self.base_url}/product/add",
                headers=self._headers(),
                data=json.dumps(data),
                timeout=30
            )
            result = resp.json()
            self._connected = True
            return f"Stored to long-term memory: {json.dumps(result)[:200]}"
        except requests.ConnectionError:
            self._connected = False
            return (f"MemOS not reachable at {self.base_url}. "
                    f"Memory not saved. Start MemOS Docker to enable persistent memory.")
        except Exception as e:
            return f"Failed to store memory: {e}"
    
    def recall(self, query: str, limit: int = 5) -> str:
        """
        Search long-term memory for relevant past context.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            Relevant memories or error message
        """
        if not self._available:
            return "Long-term memory unavailable: 'requests' not installed."
        
        data = {
            "query": query,
            "user_id": self.user_id,
            "mem_cube_id": self.cube_id
        }
        
        try:
            resp = requests.post(
                f"{self.base_url}/product/search",
                headers=self._headers(),
                data=json.dumps(data),
                timeout=30
            )
            result = resp.json()
            self._connected = True
            
            # Format results
            if isinstance(result, dict) and "results" in result:
                memories = result["results"][:limit]
                if not memories:
                    return f"No relevant long-term memories found for: '{query}'"
                
                lines = [f"Found {len(memories)} relevant memory(ies):"]
                for i, mem in enumerate(memories, 1):
                    content = mem.get("content", mem.get("text", str(mem)))
                    lines.append(f"  {i}. {content[:300]}")
                return "\n".join(lines)
            
            return f"Memory search result: {json.dumps(result)[:500]}"
            
        except requests.ConnectionError:
            self._connected = False
            return (f"MemOS not reachable at {self.base_url}. "
                    f"No persistent memories available.")
        except Exception as e:
            return f"Failed to recall memory: {e}"
    
    def forget(self, memory_id: str) -> str:
        """
        Delete a specific memory.
        
        Args:
            memory_id: ID of the memory to delete
            
        Returns:
            Confirmation or error message
        """
        if not self._available:
            return "Long-term memory unavailable: 'requests' not installed."
        
        try:
            resp = requests.delete(
                f"{self.base_url}/product/{memory_id}",
                headers=self._headers(),
                timeout=10
            )
            return f"Deleted memory {memory_id}: {resp.status_code}"
        except Exception as e:
            return f"Failed to delete memory: {e}"
    
    def status(self) -> str:
        """Get the status of the long-term memory system."""
        return (
            f"Long-Term Memory (MemOS)\n"
            f"  Server: {self.base_url}\n"
            f"  User ID: {self.user_id[:8]}...\n"
            f"  Cube ID: {self.cube_id[:8]}...\n"
            f"  Connected: {self._connected}\n"
            f"  Library available: {self._available}"
        )
