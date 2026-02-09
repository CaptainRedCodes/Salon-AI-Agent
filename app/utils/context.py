from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ContextConfig:
    """Configuration for context management."""
    max_messages: int = 15  # Keep last 15 messages
    max_context_tokens: int = 4000  
    summarize_threshold: int = 10  
    clear_tool_results_after: int = 5  
    preserve_system_messages: bool = True  
    preserve_last_tool_call: bool = True  


class ConversationContextManager:
    """
    Manages conversation history to prevent context bloat.
    
    """
    
    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
        self._message_count = 0
        self._summarized_context: Optional[str] = None
    
    def trim_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Trim conversation history to prevent context bloat.
        
        Args:
            messages: List of conversation messages
            
        Returns:
            Trimmed list of messages
        """
        if len(messages) <= self.config.max_messages:
            return messages
        
        trimmed = []
        
        # Separate system messages from others
        system_messages = []
        other_messages = []
        
        for msg in messages:
            role = msg.get("role", "")
            if role == "system" and self.config.preserve_system_messages:
                system_messages.append(msg)
            else:
                other_messages.append(msg)
        
        # Keep system messages
        trimmed.extend(system_messages)
        
        # Keep the most recent messages
        keep_count = self.config.max_messages - len(system_messages)
        if keep_count > 0:
            recent_messages = other_messages[-keep_count:]
            trimmed.extend(recent_messages)
        
        dropped_count = len(messages) - len(trimmed)
        if dropped_count > 0:
            logger.info(f"Trimmed {dropped_count} old messages from context")
        
        return trimmed
    
    def clear_tool_results(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Clear tool results from old messages to reduce token usage.
        Keeps only the most recent tool results.
        
        Args:
            messages: List of conversation messages
            
        Returns:
            Messages with old tool results cleared
        """
        if not messages:
            return messages
        
        result = []
        tool_result_count = 0
        
        # Process in reverse to count from most recent
        for i, msg in enumerate(reversed(messages)):
            role = msg.get("role", "")
            
            if role == "tool":
                tool_result_count += 1
                if tool_result_count > self.config.clear_tool_results_after:
                    # Clear old tool results, replace with summary
                    msg = msg.copy()
                    tool_name = msg.get("name", "tool")
                    msg["content"] = f"[Previous {tool_name} result cleared for context optimization]"
                    logger.debug(f"Cleared old tool result: {tool_name}")
            
            result.append(msg)
        
        return list(reversed(result))
    
    def optimize_context(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply all context optimizations.
        
        Args:
            messages: List of conversation messages
            
        Returns:
            Optimized list of messages
        """
        # First trim to max messages
        messages = self.trim_messages(messages)
        
        # Then clear old tool results
        messages = self.clear_tool_results(messages)
        
        self._message_count = len(messages)
        
        return messages
    
    def should_summarize(self, messages: List[Dict[str, Any]]) -> bool:
        """Check if we should summarize old context."""
        return len(messages) >= self.config.summarize_threshold
    
    def create_context_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Create a brief summary of the conversation for context preservation.
        This is useful when you need to significantly reduce context size.
        
        Args:
            messages: List of conversation messages
            
        Returns:
            Summary string
        """
        # Extract key information from messages
        summary_parts = []
        
        customer_name = None
        customer_phone = None
        service = None
        appointment_date = None
        appointment_time = None
        
        for msg in messages:
            content = msg.get("content", "")
            
            # Simple extraction (could be enhanced with NLP)
            if isinstance(content, str):
                content_lower = content.lower()
                
                # Look for booking-related info
                if "name" in content_lower and ":" in content:
                    # Try to extract name
                    pass
                if "phone" in content_lower:
                    pass
                if any(s in content_lower for s in ["haircut", "coloring", "styling"]):
                    pass
        
        # Build summary
        summary = "Previous conversation summary:\n"
        if customer_name:
            summary += f"- Customer: {customer_name}\n"
        if customer_phone:
            summary += f"- Phone: {customer_phone}\n"
        if service:
            summary += f"- Requested service: {service}\n"
        if appointment_date:
            summary += f"- Date: {appointment_date}\n"
        if appointment_time:
            summary += f"- Time: {appointment_time}\n"
        
        if summary == "Previous conversation summary:\n":
            summary = "Customer is inquiring about salon services."
        
        self._summarized_context = summary
        return summary
    
    def get_stats(self) -> Dict[str, Any]:
        """Get context management statistics."""
        return {
            "current_message_count": self._message_count,
            "max_messages": self.config.max_messages,
            "has_summary": self._summarized_context is not None,
        }


# Module-level instance for easy access
_context_manager: Optional[ConversationContextManager] = None


def get_context_manager() -> ConversationContextManager:
    """Get or create the context manager singleton."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ConversationContextManager()
    return _context_manager


def optimize_conversation_context(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convenience function to optimize conversation context.
    
    Args:
        messages: List of conversation messages
        
    Returns:
        Optimized messages
    """
    manager = get_context_manager()
    return manager.optimize_context(messages)
