"""Portal Workflow Recorder — Workflow Serializer.

Converts normalized RecordedSteps into Workflow YAML definitions
suitable for the ExecutionEngine.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from src.portal.recorder.models import RecordedStep, Workflow, WorkflowStep
from src.portal.recorder.exceptions import SerializationError

logger = logging.getLogger("insuredesk.recorder.serializer")

# Action mapping: RecordedStep action → WorkflowStep action
ACTION_MAP: Dict[str, str] = {
    "navigate": "navigate",
    "fill": "fill",
    "click": "click",
    "select": "select",
    "submit": "submit",
    "wait": "wait",
}


class WorkflowSerializer:
    """Serializes recorded steps into Workflow definitions and YAML.

    Usage:
        serializer = WorkflowSerializer()
        workflow = serializer.to_workflow(steps, portal="great_eastern")
        yaml_str = serializer.to_yaml(workflow)
        serializer.save_yaml(workflow, "portals/great_eastern_quote.yaml")
    """

    def to_workflow(
        self,
        steps: List[RecordedStep],
        portal: str,
        name: Optional[str] = None,
    ) -> Workflow:
        """Convert normalized steps into a Workflow object.

        Args:
            steps: Normalized RecordedSteps
            portal: Portal name
            name: Optional workflow name

        Returns:
            A Workflow ready for YAML serialization
        """
        workflow_name = name or f"{portal}_recorded_workflow"

        workflow = Workflow(
            name=workflow_name,
            portal=portal,
        )

        for i, step in enumerate(steps):
            action = ACTION_MAP.get(step.action, step.action)
            params: Dict[str, Any] = {}

            if step.selector:
                params["selector"] = step.selector
            if step.value is not None:
                params["value"] = step.value
            if step.target:
                params["target"] = step.target

            ws = WorkflowStep(
                action=action,
                parameters=params,
                wait_after_ms=step.wait_after_ms,
            )
            workflow.add_step(ws)

        return workflow

    def to_yaml(self, workflow: Workflow) -> str:
        """Serialize a Workflow to YAML string.

        Uses manual YAML generation to avoid PyYAML dependency
        and produce clean, human-readable output.

        Args:
            workflow: The Workflow to serialize

        Returns:
            YAML string
        """
        lines: List[str] = []
        lines.append(f"name: {workflow.name}")
        lines.append(f"portal: {workflow.portal}")
        lines.append(f"version: {workflow.version}")
        lines.append("steps:")

        for i, step in enumerate(workflow.steps):
            lines.append(f"  - id: step_{i + 1:02d}")
            lines.append(f"    action: {step.action}")

            if step.parameters:
                lines.append("    parameters:")
                for key, value in step.parameters.items():
                    if isinstance(value, str):
                        lines.append(f"      {key}: \"{value}\"")
                    else:
                        lines.append(f"      {key}: {value}")

            if step.wait_after_ms != 500:
                lines.append(f"    wait_after_ms: {step.wait_after_ms}")

        return "\n".join(lines)

    def save_yaml(
        self,
        workflow: Workflow,
        filepath: str,
    ) -> str:
        """Save a Workflow to a YAML file.

        Args:
            workflow: The Workflow to save
            filepath: Output file path

        Returns:
            The absolute path to the saved file

        Raises:
            SerializationError: If the file cannot be written
        """
        try:
            filepath = os.path.expanduser(filepath)
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            yaml_content = self.to_yaml(workflow)
            with open(filepath, "w") as f:
                f.write(yaml_content)
            logger.info("Workflow saved: %s (%d steps)", filepath, workflow.step_count)
            return os.path.abspath(filepath)
        except OSError as e:
            raise SerializationError(f"Failed to save workflow: {e}")
