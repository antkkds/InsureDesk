"""InsureDesk — Capture Mode Tool.

LLM-callable wrapper around the portal CaptureEngine.
Lets an assistant start/stop capture sessions and generate
portal profiles (YAML selector maps) from live portal interactions.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.tools.base import ToolBase
from src.tools.models import ToolExecutionResult


class CaptureModeTool(ToolBase):
    """Tool to capture live portal elements into a reusable profile."""

    name: str = "capture_mode"
    description: str = (
        "Start or stop portal capture mode. While active, elements clicked "
        "in the portal are recorded. Stop returns a generated portal profile."
    )

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        action = arguments.get("action", "status")
        engine = (context or {}).get("browser_engine")
        url = arguments.get("url", "")

        if action == "start":
            if engine is None:
                return ToolExecutionResult.fail(
                    error="No browser engine in context",
                    error_code="NO_ENGINE",
                )
            from src.portal.capture import CaptureSession

            session = CaptureSession(engine)
            await session.run(url, timeout=600, quiet=True)
            return ToolExecutionResult.ok(data={"status": "capturing"})

        if action == "stop":
            if engine is None:
                return ToolExecutionResult.fail(
                    error="No browser engine in context",
                    error_code="NO_ENGINE",
                )
            from src.portal.capture import CaptureSession

            session = CaptureSession(engine)
            profile = await session.run(url, timeout=1, quiet=True)
            return ToolExecutionResult.ok(
                data={"profile_yaml": profile.to_yaml() if profile else None}
            )

        return ToolExecutionResult.ok(data={"status": "idle"})
