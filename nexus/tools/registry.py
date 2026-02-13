
import inspect
import json
from typing import Callable, Dict, Any, List, get_type_hints

class ToolRegistry:
    """
    Registry for Agent Tools.
    Automatically generates JSON schemas from Python functions.
    """
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: List[Dict[str, Any]] = []

    def register(self, func: Callable):
        """
        Register a function as a tool. 
        Uses docstring and type hints to build schema.
        """
        schema = self._generate_schema(func)
        name = schema["function"]["name"]
        
        self.tools[name] = func
        self.schemas.append(schema)
        print(f"[Registry] Registered tool: {name}")

    def get_tool(self, name: str) -> Callable:
        return self.tools.get(name)

    def get_schemas(self) -> List[Dict[str, Any]]:
        return self.schemas

    def _generate_schema(self, func: Callable) -> Dict[str, Any]:
        """
        Generate OpenAI-compatible JSON schema from function.
        """
        name = func.__name__
        description = (func.__doc__ or "No description.").strip()
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self': continue
            
            # Helper to map types
            py_type = type_hints.get(param_name, str)
            json_type = "string"
            if py_type == int: json_type = "integer"
            elif py_type == float: json_type = "number"
            elif py_type == bool: json_type = "boolean"
            elif py_type == list: json_type = "array"
            elif py_type == dict: json_type = "object"
            
            # Check for optional (defaults)
            is_optional = param.default != inspect.Parameter.empty
            
            parameters["properties"][param_name] = {
                "type": json_type,
                "description": f"Parameter {param_name}"
            }
            
            if not is_optional:
                parameters["required"].append(param_name)
                
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        }
