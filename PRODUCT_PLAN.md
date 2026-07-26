# InsureDesk 产品化方案：从 Playwright 到 QtWebEngine

## 架构总览

详见 [`docs/architecture/overview.md`](docs/architecture/overview.md) 和 [`docs/products/insuredesk/browser-automation.md`](docs/products/insuredesk/browser-automation.md)。

```
InsureDesk/
├── src/
│   ├── browser/                    ← NEW: 抽象层
│   │   ├── engine.py               BrowserEngine 接口
│   │   ├── playwright_engine.py    开发引擎 (今晚测试用)
│   │   ├── webengine_engine.py     产品引擎 (顾客电脑用)
│   │   └── __init__.py             工厂函数
│   ├── portal/
│   │   ├── form_engine.py          改: 用 BrowserEngine 抽象
│   │   ├── mapping.py              YAML → selector 解析
│   │   ├── session.py              Cookie 持久化
│   │   └── inspector.py            Selector 捕获工具
│   └── portals/
│       └── base.py                 PortalAdapter 基类 + 3 个 adapter
├── portals/
│   ├── great_eastern.yaml
│   ├── allianz.yaml
│   └── aia.yaml
└── main.py                         PySide6 桌面应用
```

## 双引擎策略

| | PlaywrightEngine | WebEngineEngine |
|---|---|---|
| **用途** | 开发 / 今晚测试 | 顾客电脑产品 |
| **依赖** | playwright + chromium (~300MB) | PySide6.QtWebEngine (已装) |
| **浏览器** | 外部 Chrome 窗口 | 内嵌在 InsureDesk 窗口 |
| **安装方式** | pip install playwright | 预装在 PySide6 中 |
| **顾客需下载？** | ❌ 太复杂 | ✅ 不需额外下载 |
| **Selector 兼容** | 标准 CSS | 标准 CSS (通过 JS 注入) |

## 顾客电脑 = 零额外依赖

**Windows 10/11** 的顾客只需：
1. 下载 InsureDesk.exe (PyInstaller 打包，~50MB)
2. 双击安装
3. 打开 → 选 Great Eastern → 输入账号 → 自动操作

**不需要装：**
- ❌ Playwright / Chrome / Edge
- ❌ Python
- ❌ Hermes Agent
- ❌ 任何浏览器驱动

## PyInstaller 打包方案

```bash
# 在 Windows 上执行：
pip install pyinstaller
pyinstaller --onefile --windowed \
    --add-data "portals:portals" \
    --hidden-import PySide6.QtWebEngine \
    --hidden-import PySide6.QtWebEngineWidgets \
    --hidden-import sqlalchemy \
    main.py
# 输出: dist/InsureDesk.exe (~50MB)
```

PySide6.QtWebEngine 在 Windows 上自带 Chromium，所以 .exe 自带浏览器引擎。

## 今晚测试计划（Playwright 模式）

```bash
cd ~/InsureDesk
source venv/bin/activate

# 1. 离线确认
python test_portal_live.py

# 2. 开 GE portal
python test_portal_live.py great_eastern
# → 浏览器弹窗，手动登录
# → 登录后按 Enter → session 保存

# 3. 如需捕获 UI selector
python test_portal_live.py --dev
```

## 今晚测试后要做的事

1. **确认 selector 正确** — Great Eastern UI 可能和我们 YAML 的预设不符
2. **用 Inspector 捕获真实 selector** — 一键生成 YAML
3. **测试 Policy Search / Claims / Renewal** — 看 adapter 能否操作
4. **测试 Session 持久化** — 关掉重开，看 cookie 是否自动登录

## 关键限制（产品化时注意）

| 功能 | Playwright | WebEngine | 产品方案 |
|------|-----------|-----------|---------|
| fill_text | ✅ page.type() | ✅ JS injection | OK |
| click | ✅ page.click() | ✅ JS click() | OK |
| select_option | ✅ page.select_option() | ✅ JS el.value= | OK |
| upload_file | ✅ page.set_input_files() | ❌ 安全限制 | 弹出原生文件选择框 |
| checkbox | ✅ page.is_checked() | ✅ JS el.checked | OK |
| screenshot | ✅ page.screenshot() | ✅ QWidget.grab() | OK |
| cookies | ✅ context.cookies() | ✅ document.cookie | OK (httpOnly 会少) |
| iframe | ✅ frame() | ❌ | 需要特殊处理 |
