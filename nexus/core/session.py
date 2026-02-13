
from typing import List, Dict, Any
import time

class Session:
    """
    Manages conversation history and metadata.
    """
    def __init__(self, system_prompt: str):
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        self.created_at = time.time()
        
    def add_message(self, role: str, content: str, tool_calls: List[Dict] = None, tool_call_id: str = None, **kwargs):
        msg = {"role": role, "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id
            
        # Add any other fields (like 'name' for tool messages)
        msg.update(kwargs)
            
        self.messages.append(msg)
        
    def get_history(self) -> List[Dict[str, Any]]:
        return self.messages
        
    def clear(self, keep_system: bool = True):
        if keep_system:
            self.messages = [self.messages[0]]
        else:
            self.messages = []
