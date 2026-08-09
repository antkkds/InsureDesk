#!/usr/bin/env python3
"""InsureDesk Agent Client — standalone startup (Phase 4.6 Real E2E).

Registers this InsureDesk instance as a UIP-AI Agent Provider, then runs
the heartbeat + command loop so the cloud can dispatch capabilities
(e.g. insurance.quote.calculate) to this desktop agent.

Usage:
    python run_agent.py                          # uses config/agent.yaml
    python run_agent.py --endpoint http://127.0.0.1:8000 --api-key sk-xxx
    python run_agent.py --profile real_validation # load E2E profile

Config (config/agent.yaml):
    agent:
      endpoint: "http://127.0.0.1:8000"   # UIP-AI platform URL
      tenant_id: "default"
      api_key: "sk-..."                    # UIP-AI platform API key
      name: "Default Agent"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is on path (dev + PyInstaller bundle)
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("run_agent")

try:
    import yaml
except ImportError:
    yaml = None


def load_config(args) -> dict:
    """Load config from config/agent.yaml (or CLI overrides)."""
    cfg_path = PROJECT_ROOT / "config" / "agent.yaml"
    cfg: dict = {}
    if cfg_path.exists() and yaml is not None:
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception as e:  # pragma: no cover
            logger.warning("Could not read %s: %s", cfg_path, e)

    agent_cfg = cfg.get("agent", {}) if isinstance(cfg, dict) else {}
    net_cfg = cfg.get("network", {}) if isinstance(cfg, dict) else {}

    # CLI overrides win
    endpoint = args.endpoint or agent_cfg.get("endpoint") or net_cfg.get("bridge_url", "")
    api_key = args.api_key or agent_cfg.get("api_key", "")
    tenant_id = args.tenant_id or agent_cfg.get("tenant_id", "default")
    name = agent_cfg.get("name", "Default Agent")

    return {
        "endpoint": endpoint,
        "api_key": api_key,
        "tenant_id": tenant_id,
        "name": name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="InsureDesk Agent Client")
    parser.add_argument("--endpoint", default=os.environ.get("UIP_ENDPOINT", ""))
    parser.add_argument("--api-key", default=os.environ.get("UIP_API_KEY", ""))
    parser.add_argument("--tenant-id", default=os.environ.get("UIP_TENANT_ID", ""))
    parser.add_argument("--profile", default=os.environ.get("AGENT_PROFILE", ""))
    parser.add_argument("--once", action="store_true",
                        help="Register + poll a few times then exit (for testing)")
    args = parser.parse_args()

    cfg = load_config(args)
    if not cfg["endpoint"]:
        logger.error("No endpoint configured. Set config/agent.yaml [agent.endpoint] or --endpoint.")
        return 1
    if not cfg["api_key"]:
        logger.error("No api_key configured. Set config/agent.yaml [agent.api_key] or --api-key.")
        return 1

    from src.agent.client import AgentClient, AgentClientConfig
    from src.agent.command_loop import AgentCommandLoop
    from src.agent.e2e_profile import E2EProfile, E2EProfileEnforcer, DEFAULT_PROFILE
    from src.agent.handlers import CapabilityHandlerRegistry
    from src.agent.heartbeat import AgentHeartbeat
    from src.agent.manifest import InsureDeskManifest
    from src.agent.result_reporter import ResultReporter
    from src.agent.trace import ExecutionTracer, execution_tracer

    client_config = AgentClientConfig(
        endpoint=cfg["endpoint"],
        tenant_id=cfg["tenant_id"],
        api_key=cfg["api_key"],
        timeout=10.0,
        verify_ssl=False,  # local dev
    )
    manifest = InsureDeskManifest(
        metadata={"agent_name": cfg["name"]}
    )
    client = AgentClient(client_config, manifest=manifest)

    # Register
    instance_id = client.register()
    logger.info("✅ Registered agent instance=%s name=%s tenant=%s",
                instance_id, cfg["name"], cfg["tenant_id"])

    # Heartbeat thread
    hb = AgentHeartbeat(client.heartbeat, interval_seconds=30, max_retries=3)
    hb.start()

    # E2E profile
    profile = (
        E2EProfile.from_file(args.profile)
        if args.profile and Path(args.profile).exists()
        else E2EProfile.from_dict(DEFAULT_PROFILE)
    )
    enforcer = E2EProfileEnforcer(profile)
    logger.info("🔒 E2E profile: %s (mode=%s permission=%s)",
                profile.name, profile.mode, profile.permission)

    # Handlers
    handlers = CapabilityHandlerRegistry()
    handlers.register_defaults()

    # Wire tracer
    tracer = ExecutionTracer()

    # Command loop
    loop = AgentCommandLoop(
        client, handlers,
        poll_interval_seconds=5.0,
        enforcer=enforcer,
        tracer=tracer,
    )
    loop.start()
    logger.info("🔄 Command loop started — listening for capabilities...")

    if args.once:
        time.sleep(15)
        loop.stop()
        hb.stop()
        logger.info("--once finished")
        return 0

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        loop.stop()
        hb.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
