"""InsureDesk — Tool Calling Runtime.

Tools are callable units that an LLM Assistant can invoke.
Each tool has:
- name: unique identifier
- description: natural language description for LLM routing
- parameters: JSON Schema defining expected arguments
- execute(): async implementation

Usage:
    from src.tools.registry import ToolRegistry
    registry = ToolRegistry.get_instance()
    result = await registry.execute("create_quote", {
        "proposer_name": "Tiong Hoe Hung",
        "risk_class": "fire",
    })
"""
