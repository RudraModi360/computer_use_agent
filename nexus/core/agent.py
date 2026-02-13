import json
import time
import os
import asyncio
from typing import List, Dict, Any, Optional

# Config
from nexus.config import config

# Components
from nexus.memory.rag import SemanticMemory
from nexus.core.session import Session
from nexus.core.llm import OllamaProvider, LlamaCppProvider
from nexus.tools.registry import ToolRegistry
from nexus.tools.shell import run_shell

class NexusAgent:
    """
    Nexus: A Semantic, Shell-Integrated Autonomous Agent.
    Refactored for robustness using Reference Patterns.
    """
    def __init__(self):
        # 1. Initialize Components
        print(f"[Nexus] Loading Semantic Memory ({config.EMBEDDING_MODEL})...")
        self.memory = SemanticMemory()
        
        print(f"[Nexus] Loading Tool Registry...")
        self.registry = ToolRegistry()
        self.registry.register(run_shell)
        
        print(f"[Nexus] Initializing LLM Provider ({config.LLM_PROVIDER})...")
        if config.LLM_PROVIDER == "ollama":
            self.llm = OllamaProvider()
        elif config.LLM_PROVIDER == "llamacpp":
            self.llm = LlamaCppProvider()
        else:
            raise ValueError(f"Unknown Provider: {config.LLM_PROVIDER}")
            
        # 2. Initialize Session
        self.session = Session(self._get_system_prompt())

    def _get_system_prompt(self) -> str:
        return f"""# ROLE: Nexus
Nexus is an advanced, shell-integrated autonomous agent designed for high-precision data management and system automation.

# DESCRIPTION
You operate within a Windows environment with direct access to the local filesystem and persistent semantic memory. You act as a bridge between natural language intent and technical execution, capable of managing complex workflows involving local datasets and system operations.

# TOOLS & CAPABILITIES
1. **Shell Integration (`run_shell`)**: Execute Windows CMD/PowerShell commands. Use for file manipulation, directory traversal (`dir`), and reading file content.
2. **Semantic Memory**: You are provided with a `RELEVANT MEMORY` block containing past context. Trust this data as the source of truth for recurring tasks and entity relationships.

# USAGE & DOMAIN KNOWLEDGE
- **Data Repository**: Primary data is located in `{os.getcwd()}` .
- **System Info & Apps Info** : use shell to gather all system required information if needed . 
- **Key Files**:
    - `Emails_Supplier.xlsx`: Official directory for Supplier Names, Emails, and Contact Persons.
    - `Products.xlsx`: Inventory data including PIP, EAN, and 'Current Lowest' pricing.
- **Supplier Mapping**: The 'Current Lowest' column in `Products.xlsx` contains short names. You must cross-reference these with `Emails_Supplier.xlsx` to resolve the full official supplier name.

# PURPOSE
To provide an autonomous, context-aware interface for managing supplier relations, inventory tracking, and system-level tasks while maintaining data integrity across local Excel datasets.

# CRITICAL CONSTRAINTS (What to care about)
- **Naming Integrity**: Always use FULL supplier names from `Emails_Supplier.xlsx` when updating master files; short names are for reference only.
- **Path Persistence**: Reuse known file paths from memory to avoid redundant directory scanning.
- **Precision**: When drafting emails or updates, ensure product names and pricing are matched exactly as found in the source files.
- **Safety**: Perform non-destructive shell operations unless explicitly instructed otherwise.

# OPERATIONAL METHODOLOGY
1. **Identify**: Determine if the task requires data retrieval, file modification, or system exploration.
2. **Context Retrieval**: Check `RELEVANT MEMORY` first. If missing, use `dir D:\\Client-Data\\` to locate necessary files.
3. **Data Pipeline**: 
    - To find contact info for a product: Search `Products.xlsx` -> Extract supplier short name -> Map to full name in `Emails_Supplier.xlsx` -> Retrieve Email.
4. **Execution**: Formulate the specific Windows command or response. If drafting an email, proceed directly to the draft once the supplier email is identified.
"""

    def chat(self, user_input: str) -> str:
        """
        Main interaction loop with RAG and Retry logic.
        """
        # 1. Retrieve Context (RAG)
        context_chunks = self.memory.retrieve(user_input, top_k=config.MAX_CONTEXT_CHUNKS)
        context_str = "\n\n".join([f"- {c['text']} (Source: {c['metadata'].get('source', 'unknown')})" for c in context_chunks])
        if not context_str: context_str = "No relevant past memories found."
        
        print(f"\n[Nexus] Retrieved Context:\n{context_str[:200]}...\n")

        # 2. Update Session
        # Inject context into the *latest* system message or as a temporary system message
        # For simplicity, we append it as a temporary system message for this turn
        self.session.add_message("user", user_input)
        
        # Prepare messages for LLM (including context)
        history = self.session.get_history()
        messages_with_context = [
            history[0], # System Prompt
            {"role": "system", "content": f"RELEVANT MEMORY:\n{context_str}"}
        ] + history[1:]
        
        # 3. Generate & Loop (Think -> Act)
        # We allow up to 5 turns of tool usage
        final_response_content = ""
        
        for turn in range(5):
            try:
                # Call LLM
                response = self.llm.chat(messages_with_context, tools=self.registry.get_schemas())
                
                # Handle Response
                # Different providers return different objects, we expect an OpenAI-like object or dict
                # Basic normalization:
                if hasattr(response, 'choices'):
                    msg = response.choices[0].message
                    content = msg.content
                    tool_calls = msg.tool_calls
                else:
                    # Fallback for dict (LlamaCpp sometimes)
                     msg = response['choices'][0]['message']
                     content = msg['content']
                     tool_calls = msg.get('tool_calls')

                # Add Assistant Message to History
                # We need to construct a dict for the session
                assistant_msg = {"role": "assistant", "content": content}
                if tool_calls:
                     # Serialize tool calls if they are objects
                     serialized_tcs = []
                     for tc in tool_calls:
                         if hasattr(tc, 'model_dump'): serialized_tcs.append(tc.model_dump())
                         elif hasattr(tc, 'dict'): serialized_tcs.append(tc.dict())
                         else: serialized_tcs.append(tc)
                     assistant_msg["tool_calls"] = serialized_tcs
                
                self.session.add_message(**assistant_msg)
                messages_with_context.append(assistant_msg) # Update local context
                
                # Check for Tool Calls
                if tool_calls:
                    print(f"[Nexus] Tool Calls: {len(tool_calls)}")
                    for tc in tool_calls:
                        # Parse Tool Call
                        if hasattr(tc, 'function'):
                             func_name = tc.function.name
                             args_str = tc.function.arguments
                             tc_id = tc.id
                        else:
                             func_name = tc['function']['name']
                             args_str = tc['function']['arguments']
                             tc_id = tc.get('id')
                        
                        try:
                            args = json.loads(args_str)
                            print(f"[Nexus] Executing {func_name} with {args}...")
                            
                            # Execute
                            tool_func = self.registry.get_tool(func_name)
                            if tool_func:
                                result = tool_func(**args)
                            else:
                                result = f"Error: Tool {func_name} not found."
                                
                        except Exception as e:
                            result = f"Error executing tool: {e}"
                            
                        print(f"[Nexus] Result: {str(result)[:100]}...")
                        
                        # Add Tool Output
                        tool_msg = {
                            "role": "tool", 
                            "content": str(result),
                            "tool_call_id": tc_id,
                            "name": func_name
                        }
                        self.session.add_message(**tool_msg)
                        messages_with_context.append(tool_msg)
                        
                    # Loop back to LLM to process results
                    continue
                else:
                    # No tool calls, we are done
                    final_response_content = content
                    break
                    
            except Exception as e:
                print(f"[Nexus] Error in loop: {e}")
                final_response_content = f"I encountered an error: {e}"
                break

        # 4. Memorize
        if self._is_worth_remembering(user_input, final_response_content):
            print("[Nexus] Saving interaction to memory.")
            self.memory.add_memory(f"User: {user_input}\nNexus: {final_response_content}")
            
        return final_response_content

    def _is_worth_remembering(self, user_input: str, response: str) -> bool:
        """
        Filter out trivial interactions AND errors.
        """
        # 1. Check for Errors in response
        if "I encountered an error" in response or "Error executing tool" in response:
            return False
            
        if not response: return False
        
        # 2. Check for Trivial Inputs
        if len(user_input.strip()) < 5 and user_input.lower().strip() in ['hi', 'hello', 'ok', 'thanks', 'cool']: 
            return False
        
        # 3. LLM Check
        prompt = f"""Analyze this interaction value for long-term memory.

User: {user_input}
Agent: {response[:500]}...

Does this contain useful facts, preferences, code logic, or project details?
Or is it trivial chitchat, simple navigation (dir, cd), or errors?

Reply with exactly ONE word: SAVE or DISCARD."""

        try:
            # We use a separate lightweight call here if needed, or just rely on heuristics
            # For now, let's trust the error check + length check mainly, 
            # and maybe skip LLM call for "dir" commands to save time
            if "dir" in user_input.lower() or "ls" in user_input.lower():
                 return False

            return True 
        except:
            return True

if __name__ == "__main__":
    agent = NexusAgent()
    while True:
        u = input("User: ")
        if u == "exit": break
        print(agent.chat(u))
