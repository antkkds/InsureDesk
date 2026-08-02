"""InsureDesk — Agent Client Runtime (Phase 4.3).

Makes InsureDesk the first UIP-AI Agent Protocol CLIENT:

    UIP-AI (Agent Protocol Server)
        ↓ http_pull
    InsureDesk Agent Client Runtime (this package)
        ↓
    Local execution (existing QuoteExecutor / ToolRegistry / Portal)
        ↓
    Result callback

This is a THIN layer — it does NOT change the existing Portal Automation
Engine, BridgeServer (8199), or the local 9876 API.
"""

from src.agent.client import AgentClient, AgentClientConfig, AgentCommand
from src.agent.command_loop import AgentCommandLoop
from src.agent.handlers import (
    CapabilityHandler,
    CapabilityHandlerRegistry,
    QuoteCapabilityHandler,
)
from src.agent.heartbeat import AgentHeartbeat
from src.agent.manifest import InsureDeskManifest
from src.agent.result_reporter import ResultReporter, map_error_code

__all__ = [
    "AgentClient",
    "AgentClientConfig",
    "AgentCommand",
    "AgentCommandLoop",
    "CapabilityHandler",
    "CapabilityHandlerRegistry",
    "QuoteCapabilityHandler",
    "AgentHeartbeat",
    "InsureDeskManifest",
    "ResultReporter",
    "map_error_code",
]
