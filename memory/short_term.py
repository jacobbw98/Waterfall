"""
Short-Term Memory — powered by Recursive Language Models (RLM).

Stores tool results, conversation snippets, and documents as named context
variables that the agent can search, peek, and summarize recursively.
RLM processes these through a Python REPL, allowing the LLM to explore
contexts of unlimited size without stuffing them into the prompt.
"""
import sys
import os
from typing import Optional, Dict

# Add vendor RLM to path
_rlm_path = os.path.join(os.path.dirname(__file__), '..', 'vendor', 'recursive-llm', 'src')
if os.path.isdir(_rlm_path):
    sys.path.insert(0, os.path.abspath(_rlm_path))

try:
    from rlm import RLM
    RLM_AVAILABLE = True
except Exception as e:
    print(f"[ShortTermMemory] Failed to load RLM: {e}")
    RLM_AVAILABLE = False


class ShortTermMemory:
    """
    Within-session memory using RLM for unbounded context processing.
    
    Stores named context chunks (tool results, documents, conversation history)
    and lets the LLM recursively search/explore them without exceeding the
    context window.
    """
    
    def __init__(self, model: str = "nemotron-3-nano:latest"):
        """
        Initialize short-term memory.
        
        Args:
            model: Ollama model name (will be prefixed with 'ollama/' for RLM/LiteLLM)
        """
        self.contexts: Dict[str, str] = {}
        self._model = model
        self._rlm_model = f"ollama/{model}" if not model.startswith("ollama/") else model
        self._available = RLM_AVAILABLE
        
        if not self._available:
            print("[ShortTermMemory] WARNING: recursive-llm not installed. "
                  "Run: pip install -e vendor/recursive-llm")
    
    @property
    def available(self) -> bool:
        return self._available
    
    def store(self, key: str, content: str) -> str:
        """
        Store a named context chunk.
        
        Args:
            key: Identifier for this context (e.g., 'tool_result_3', 'document_1')
            content: The text content to store
            
        Returns:
            Confirmation message
        """
        self.contexts[key] = content
        total_chars = sum(len(v) for v in self.contexts.values())
        return (f"Stored '{key}' ({len(content)} chars). "
                f"Total memory: {len(self.contexts)} items, {total_chars} chars.")
    
    def peek(self, key: str, start: int = 0, end: int = 1000) -> str:
        """
        Peek at a slice of a stored context.
        
        Args:
            key: Context identifier
            start: Start character index
            end: End character index
            
        Returns:
            The requested slice, or error message
        """
        if key not in self.contexts:
            available = ", ".join(self.contexts.keys()) if self.contexts else "(empty)"
            return f"Key '{key}' not found. Available: {available}"
        
        content = self.contexts[key]
        return content[start:end]
    
    def list_keys(self) -> str:
        """List all stored context keys with their sizes."""
        if not self.contexts:
            return "Short-term memory is empty."
        
        lines = []
        for key, content in self.contexts.items():
            lines.append(f"  - {key}: {len(content)} chars")
        return "Stored contexts:\n" + "\n".join(lines)
    
    def search(self, query: str) -> str:
        """
        Search across all stored contexts using RLM's recursive exploration.
        
        If RLM is not available, falls back to simple substring search.
        
        Args:
            query: What to search for
            
        Returns:
            Relevant findings from stored context
        """
        if not self.contexts:
            return "Short-term memory is empty. Nothing to search."
        
        # Build combined context with clear separators
        combined = self._build_combined_context()
        
        if self._available:
            try:
                rlm = RLM(
                    model=self._rlm_model,
                    max_depth=3,
                    max_iterations=15
                )
                result = rlm.complete(
                    query=f"Search the following stored memory contexts and find information relevant to: {query}",
                    context=combined
                )
                return result
            except Exception as e:
                print(f"[ShortTermMemory] RLM search failed, falling back to simple search: {e}")
        
        # Fallback: simple substring search
        return self._simple_search(query)
    
    def summarize(self, query: str = "Summarize everything stored in memory.") -> str:
        """
        Use RLM to summarize stored contexts with respect to a query.
        
        Args:
            query: Focus question for the summary
            
        Returns:
            Summary text
        """
        if not self.contexts:
            return "Short-term memory is empty. Nothing to summarize."
        
        combined = self._build_combined_context()
        
        if self._available:
            try:
                rlm = RLM(
                    model=self._rlm_model,
                    max_depth=3,
                    max_iterations=15
                )
                result = rlm.complete(query=query, context=combined)
                return result
            except Exception as e:
                return f"RLM summarization failed: {e}. Memory has {len(self.contexts)} items."
        
        # Fallback: just return truncated contents
        return f"RLM not available. Memory contains {len(self.contexts)} items:\n{combined[:2000]}"
    
    def clear(self) -> str:
        """Clear all stored contexts."""
        count = len(self.contexts)
        self.contexts.clear()
        return f"Cleared {count} items from short-term memory."
    
    def _build_combined_context(self) -> str:
        """Combine all stored contexts into one searchable string."""
        parts = []
        for key, content in self.contexts.items():
            parts.append(f"=== CONTEXT: {key} ===\n{content}\n=== END: {key} ===")
        return "\n\n".join(parts)
    
    def _simple_search(self, query: str) -> str:
        """Fallback substring search when RLM is unavailable."""
        query_lower = query.lower()
        results = []
        
        for key, content in self.contexts.items():
            content_lower = content.lower()
            if query_lower in content_lower:
                # Find the matching region and extract a snippet
                idx = content_lower.index(query_lower)
                start = max(0, idx - 100)
                end = min(len(content), idx + len(query) + 100)
                snippet = content[start:end]
                results.append(f"[{key}]: ...{snippet}...")
        
        if results:
            return f"Found {len(results)} match(es):\n" + "\n".join(results)
        return f"No matches found for '{query}' across {len(self.contexts)} stored contexts."
