"""Base Tool class for all agent tools."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime


@dataclass
class ToolResult:
    """Result from tool execution."""
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict = field(default_factory=dict)
    
    def __str__(self):
        if self.success:
            return f"✅ {self.output}"
        return f"❌ {self.error}"


class BaseTool(ABC):
    """Abstract base class for all tools."""
    
    name: str = "base_tool"
    description: str = "Base tool"
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    def get_schema(self) -> Dict:
        """Get JSON schema for tool parameters."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {}
        }
    
    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"
