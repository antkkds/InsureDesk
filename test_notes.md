# InsureDesk Portal Test — 今晚操作指南

## 架构已升级：双引擎就绪

```
BrowserEngine (抽象层)
├── PlaywrightEngine  ← 开发测试（今晚用）
└── WebEngineEngine   ← 产品（顾客 Windows 电脑，零额外依赖）
```

✅ **197 个测试全部通过**
✅ **两个引擎都可创建**
✅ **今晚用 Playwright 测试** → **产品化自动切到 WebEngine**

---

## 快速启动

### 1. 激活环境
```bash
cd ~/InsureDesk
source venv/bin/activate
```

### 2. 先跑离线确认（不打开浏览器）
```bash
python test_portal_live.py
```
预期输出：3 个 Portal 全部 ✅ 通过

### 3. 开浏览器测 Great Eastern
```bash
python test_portal_live.py great_eastern
```
- 浏览器自动打开 GE i-Connect 登录页
- **你手动输入账号密码登录**
- 登录后按 Enter → session 保存（下次不用再登录）

### 4. 如果 UI 对不上（selector 失效）
```bash
python test_portal_live.py --dev
```
选择 great_eastern → 打开浏览器 → 点要捕获的元素 → 退出时自动保存 YAML

---

## 产品化路线（你说得对的方向）

| 阶段 | 引擎 | 需装什么 | 给谁用 |
|------|------|---------|--------|
| 今晚测试 | Playwright | pip install playwright + chromium | 我们 |
| MVP 发布 | Qt WebEngine | 只需要 PySide6（已有） | 顾客 |
| 最终安装包 | PyInstaller .exe | 只需要 Windows 10/11 | 顾客双击安装 |

**顾客电脑不需要：**
- ❌ Playwright
- ❌ Chrome / Edge
- ❌ Python
- ❌ Hermes Agent
- ❌ 任何浏览器驱动

**只需要一个 .exe 安装包**（PyInstaller 打包，~50MB）

详见 `PRODUCT_PLAN.md` 和 [`docs/products/insuredesk/PILOT.md`](docs/products/insuredesk/PILOT.md)

---

## 测试要点

1. **看能不能登录** Great Eastern i-Connect
2. **看 selector 对不对** — 预设的 #username / #password / button[type='submit']
3. **测 Policy Search** — 搜一个保单号
4. **测 Session** — 关掉重开，看 cookie 能不能自动登录
5. **如果预设不对** → 用 Inspector 捕获真实 selector
