#!/usr/bin/env python3
"""InsureDesk Portal Live Test — 交互式测试脚本

用法：
    source venv/bin/activate
    python test_portal_live.py        # 跑所有测试
    python test_portal_live.py great-eastern  # 只测 Great Eastern
    python test_portal_live.py --dev   # 打开 Inspector 开发模式
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.portal.mapping import load_portal_mapping, get_selector, list_available_portals
from src.portal.form_engine import FormEngine
from src.portal.session import PortalSession
from src.portals.base import get_adapter, list_adapters
from src.browser import create_browser_engine

import asyncio

# Adapter name -> YAML filename mapping
# The adapter_name is the underscore version used in YAML filenames
ADAPTER_NAMES = ["great_eastern", "allianz", "aia"]

PORTAL_URLS = {
    "great_eastern": {
        "name": "Great Eastern i-Connect",
        "url": "https://iconnect.greateasternlife.com",
        "mapping_file": "portals/great_eastern.yaml",
    },
    "allianz": {
        "name": "Allianz Life e-Service",
        "url": "https://life-eservice.allianz.com.my",
        "mapping_file": "portals/allianz.yaml",
    },
    "aia": {
        "name": "AIA eCare",
        "url": "https://ecare.aia.com.my",
        "mapping_file": "portals/aia.yaml",
    },
}


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_portal_offline(portal_id):
    """离线测试 — 确认 mapping 和 adapter 可以加载"""
    info = PORTAL_URLS.get(portal_id)
    if not info:
        print(f"  ❌ 未知 portal: {portal_id}")
        return False

    mapping_file = os.path.join(os.path.dirname(__file__), info["mapping_file"])
    if os.path.exists(mapping_file):
        print(f"  ✅ YAML config 存在: {info['mapping_file']}")
    else:
        print(f"  ❌ YAML config 不存在: {info['mapping_file']}")
        return False

    mapping = load_portal_mapping(portal_id)
    assert mapping is not None, "load_portal_mapping 返回 None"
    print(f"  ✅ Mapping loaded: {mapping.name}")
    print(f"     URL: {mapping.base_url or mapping.login_url or 'N/A'}")

    # 测试 selector 解析
    login_username = get_selector(mapping, "login", "username")
    print(f"  ✅ Login username selector: {login_username}")

    login_password = get_selector(mapping, "login", "password")
    print(f"  ✅ Login password selector: {login_password}")

    login_button = get_selector(mapping, "login", "submit")
    print(f"  ✅ Login button selector: {login_button}")

    # 测试 adapter
    adapter = get_adapter(portal_id)
    assert adapter is not None, "get_adapter 返回 None"
    mapping = adapter.mapping
    mapping_name = mapping.name if mapping else portal_id
    print(f"  ✅ Adapter loaded: {adapter.__class__.__name__}")
    print(f"     Portal name: {mapping_name}")
    print(f"     Has mapping: {'Yes' if adapter.mapping else 'No'}")

    return True


async def test_portal_live(portal_id, headless=False):
    """实际打开浏览器测试 — 需要用户提供登录凭证"""
    adapter = get_adapter(portal_id)
    if not adapter:
        print(f"  ❌ 无法加载 adapter: {portal_id}")
        return

    mapping = adapter.mapping
    mapping_name = mapping.name if mapping else portal_id

    print(f"  🌐 正在打开 {mapping_name}...")
    print(f"     URL: {adapter.start_url if hasattr(adapter, 'start_url') else (mapping.login_url if mapping else 'N/A')}")
    print(f"     Engine: {'playwright' if adapter.engine else 'will create'}")
    print(f"     Headless: {headless}")
    print()

    # 初始化 browser engine (优先用 Playwright，开发测试用)
    if not adapter.engine:
        engine = create_browser_engine(prefer="playwright")
        adapter.engine = engine
    else:
        engine = adapter.engine

    await engine.start(headless=headless)
    print(f"  ✅ Engine started: {engine.name}")

    ok = await engine.navigate(adapter.start_url)
    page_title = await engine.get_title()
    page_url = await engine.get_url()

    if ok:
        print(f"  ✅ 页面加载成功: {page_title}")
        print(f"     URL: {page_url}")
        print()
        print("  接下来你可以:")
        print("  1. 在浏览器中手动登录")
        print("  2. 输入你的 Great Eastern 账号密码")
        print("  3. 登录成功后按 Enter 继续...")
        input("    按 Enter 继续 > ")

        # 测试表单引擎
        print(f"\n  📝 测试表单引擎 fill_text...")
        print()

        # 保存 session
        print(f"\n  📝 保存 session...")
        cookies = await adapter.engine.get_cookies()
        adapter.session.save_cookies(portal_id, [
            {"name": c.name, "value": c.value, "domain": c.domain,
             "path": c.path, "secure": c.secure, "httpOnly": c.http_only,
             "sameSite": c.same_site, "expires": c.expires}
            for c in cookies
        ])
        print(f"  ✅ Session saved ({len(cookies)} cookies)")

        await engine.stop()
    else:
        print(f"  ❌ 页面加载失败")


async def open_inspector(headless=False):
    """打开 Browser Inspector — 捕获 selector 生成 YAML"""
    from src.portal.inspector import PortalInspector

    print("  🔍 Portal Inspector — 开发模式")
    print()
    print("  用途: 点选保险公司门户的元素，自动生成 selector")
    print()
    print("  支持的 portal:")
    for pid in list_available_portals():
        print(f"     - {pid}")

    portal_id = input(f"\n  输入 portal ID (默认 great-eastern): ").strip() or "great-eastern"

    inspector = PortalInspector(portal_id=portal_id, headless=headless)
    page = await inspector.start()

    if page:
        print(f"\n  ✅ Inspector 已启动: {page.url}")
        print(f"  💡 你现在可以在浏览器中做:")
        print(f"     1. 登录 portal")
        print(f"     2. 点击需捕获的元素")
        print(f"     3. Inspector 会记录 selector 信息")
        print(f"     4. 退出时自动保存 YAML")
        input(f"\n  完成操作后按 Enter 退出 Inspector > ")
        await inspector.stop()
        print(f"  ✅ Inspector 已关闭，mapping 已保存")


def main():
    print_header("InsureDesk Portal Test Suite")
    print(f"  Available portals: {list_available_portals()}")
    print(f"  Adapters: {[a['adapter'] for a in list_adapters()]}")

    # Parse args
    args = sys.argv[1:]
    dev_mode = "--dev" in args
    portal_id = None
    for arg in args:
        if arg in PORTAL_URLS and arg != "--dev":
            portal_id = arg
            break
    if not portal_id and args:
        # Allow user to type hyphen, we convert to underscore
        for arg in args:
            if arg.replace('-', '_') in PORTAL_URLS:
                portal_id = arg.replace('-', '_')
                break

    # Step 1: 离线测试
    if portal_id:
        print_header(f"Offline Test: {portal_id}")
        ok = test_portal_offline(portal_id)
        if not ok:
            sys.exit(1)
    else:
        for pid in ADAPTER_NAMES:
            print_header(f"Offline Test: {pid}")
            test_portal_offline(pid)

    print_header("✅ 离线测试全部通过")

    # Step 2: 实时测试
    if dev_mode:
        print_header("🔍 Inspector 开发模式")
        asyncio.run(open_inspector(headless=False))
    else:
        if portal_id:
            print_header(f"🌐 Live Test: {portal_id}")
            asyncio.run(test_portal_live(portal_id, headless=False))

    print()
    print("  🎯 完成！见 ~/InsureDesk/test_notes.md 了解详细步骤")


if __name__ == "__main__":
    main()
