"""Portal Workflow Recorder — Event Normalizer.

Converts raw RecordedEvent objects into normalized RecordedStep objects.
Handles:
- Grouping consecutive input events into fill operations
- Converting clicks into discrete step actions
- Generating wait steps between navigations
- Cleaning up duplicate or noise events
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.recorder.models import (
    EventType,
    RecordedEvent,
    RecordedStep,
)

logger = logging.getLogger("insuredesk.recorder.normalizer")

# Events to filter out during normalization
NOISE_EVENTS: List[str] = [EventType.HOVER, EventType.SCROLL]

# Minimum time gap (ms) between unrelated events
NAVIGATION_GAP_MS: int = 300


class Normalizer:
    """Converts raw CDP events into normalized RecordedSteps.

    Usage:
        normalizer = Normalizer()
        steps = normalizer.normalize(events)
    """

    def normalize(self, events: List[RecordedEvent]) -> List[RecordedStep]:
        """Convert a list of RecordedEvents into RecordedSteps.

        Processing steps:
        1. Filter out noise events (hover, scroll)
        2. Group consecutive inputs into fill actions
        3. Convert clicks to step actions
        4. Add waits for navigation events
        5. Deduplicate consecutive similar events

        Args:
            events: Raw recorded events

        Returns:
            Normalized list of RecordedSteps
        """
        # Step 1: Filter noise
        filtered = [e for e in events if e.type not in NOISE_EVENTS]

        # Step 2: Group and convert
        steps: List[RecordedStep] = []
        i = 0
        while i < len(filtered):
            event = filtered[i]

            if event.type == EventType.NAVIGATE:
                steps.append(self._navigate_to_step(event))

            elif event.type == EventType.INPUT:
                # Group consecutive inputs
                input_group = self._group_inputs(filtered, i)
                if input_group:
                    steps.extend(input_group)
                    i += len(input_group) - 1
                else:
                    steps.append(self._input_to_step(event))

            elif event.type == EventType.CLICK:
                steps.append(self._click_to_step(event))

            elif event.type == EventType.SELECT:
                steps.append(self._select_to_step(event))

            elif event.type == EventType.SUBMIT:
                steps.append(self._submit_to_step(event))

            elif event.type == EventType.WAIT:
                steps.append(self._wait_to_step(event))

            i += 1

        # Step 3: Deduplicate consecutive similar steps
        steps = self._deduplicate(steps)

        return steps

    def _group_inputs(
        self, events: List[RecordedEvent], start_idx: int
    ) -> Optional[List[RecordedStep]]:
        """Group consecutive input events into fill steps.

        If multiple inputs happen within a short time window,
        they're grouped as a single 'fill' step.
        """
        if start_idx >= len(events):
            return None
        if events[start_idx].type != EventType.INPUT:
            return None

        steps = []
        i = start_idx
        while i < len(events) and events[i].type == EventType.INPUT:
            steps.append(self._input_to_step(events[i]))
            i += 1
        return steps

    def _navigate_to_step(self, event: RecordedEvent) -> RecordedStep:
        return RecordedStep(
            action="navigate",
            target="url",
            value=event.url,
            url=event.url,
            wait_after_ms=1000,
        )

    def _input_to_step(self, event: RecordedEvent) -> RecordedStep:
        return RecordedStep(
            action="fill",
            target=event.selector or event.tag_name or "input",
            value=event.value,
            selector=event.selector,
            url=event.url,
        )

    def _click_to_step(self, event: RecordedEvent) -> RecordedStep:
        return RecordedStep(
            action="click",
            target=event.selector or event.tag_name or "button",
            selector=event.selector,
            url=event.url,
        )

    def _select_to_step(self, event: RecordedEvent) -> RecordedStep:
        return RecordedStep(
            action="select",
            target=event.selector or "select",
            value=event.value,
            selector=event.selector,
            url=event.url,
        )

    def _submit_to_step(self, event: RecordedEvent) -> RecordedStep:
        return RecordedStep(
            action="submit",
            target=event.selector or "form",
            selector=event.selector,
            url=event.url,
            wait_after_ms=2000,
        )

    @staticmethod
    def _wait_to_step(event: RecordedEvent) -> RecordedStep:
        wait_ms = 500
        if isinstance(event.value, (int, float)):
            wait_ms = int(event.value)
        return RecordedStep(action="wait", value=wait_ms, wait_after_ms=wait_ms)

    @staticmethod
    def _deduplicate(steps: List[RecordedStep]) -> List[RecordedStep]:
        """Remove consecutive steps with the same action and target."""
        if not steps:
            return steps
        result = [steps[0]]
        for step in steps[1:]:
            last = result[-1]
            if step.action == "fill" and last.action == "fill":
                if step.selector == last.selector:
                    result[-1] = step  # Replace with latest value
                    continue
            if step.action == last.action and step.target == last.target:
                continue
            result.append(step)
        return result
