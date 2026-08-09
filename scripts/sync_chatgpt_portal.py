"""Sync with ChatGPT: ask about GE two-portal keyin flow."""
import asyncio, json, sys
from playwright.async_api import async_playwright

MESSAGE = """[InsureDesk 项目 — GE 报价自动化进展 + 需要你确认 keyin 流程]

我们实测了 GEGLink（Great Eastern General 马来西亚），发现登录后 Get Quote 页面有 **两个 portal 入口**：

**Portal 1: Houseowner/Householder Quotation** (houseQuote.html)
- 用途：general 保单（家宅业主/住户保险）
- 关键字段（实测 79 个）：
  - 日期: fr_p_of_insurance / to_p_of_insurance (dd/mm/yyyy)
  - 投保人: insured_name, add1-5
  - 电话: hpExt/hpNo, homeExt/homeNo, offExt/offNo
  - 建筑类型: type_of_Building (4001 Dwellings - Detached / 4005 Flats...)
  - 构造等级: const_Classification (1A/1B/2/3)
  - 保额: h_Owner_Sum_Insured, h_Owner_Ext1/Ext2... (延伸险)
  - Contents 部分: All Contents / List of Contents 二选一

**Portal 2: Fire Quotation** (fireQuote.html)
- 用途：火险 quotation
- 关键字段（实测 111 个）：
  - 日期: f_period_from / f_period_to (dd/mm/yyyy)
  - 投保人: f_insured_name, f_add1-5
  - 电话: hpExt/hpNo, homeExt/homeNo, offExt/offNo
  - 建筑类型: f_type_building (1001 Dwellings, 1008 Flats...)
  - 构造等级: f_const_Class (1A/1B/2/3)
  - 保额: f_building, f_furniture, f_plant, f_office, f_stock, f_household, f_debris, f_rental, f_arc, f_oth_lis
  - totalSumInsured: f_total_sum_insured

**业务背景（用户 Anthony 提供）：**
- general 保单通常在 Portal 1 (houseQuote) 就能做好
- 但有些顾客需要火险（fire），就要用 Portal 2 (fireQuote) 做 quotation
- 我们的自动化用例是火险（house fire insurance）→ 应该走 Portal 2

**我们遇到的问题：**
在 Portal 2 (fireQuote.html) 填了 11 个字段（日期、name、地址、电话、occupation=1001 Dwellings、construction=1A、f_building=保额），点 Save 后：
1. 第一次报 "Please fill in the required field(s) [ Hp Ext ]" — 我们补了手机区号
2. 第二次报 "Fire quotation fail to saved"（服务器端保存失败，页面跳成 House Quotation）

**请你分析：**
1. 我们的用例（火险）确认走 Portal 2 (Fire Quotation) 对吗？还是应该走 Portal 1？
2. Portal 2 的完整必填字段 keyin 顺序是什么？（哪些字段必须填、什么格式）
3. "Fire quotation fail to saved" 最可能是什么原因？
   - 日期格式问题？
   - 手机号格式（012-3456789 → ext=012, no=3456789）？
   - 缺少某必填字段（如 debris/rental 延伸险、const_class_desc 描述）？
   - 保额字段组合问题？
   - 还是服务器端校验（比如 sum insured 最小值）？
4. 正确的 Save/Calculate 触发方式是什么？（这个表单只有 Save 按钮）

请给出具体的 keyin 建议，我们好继续自动化。"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://127.0.0.1:9230')
        ctx = browser.contexts[0]
        target = None
        for page in ctx.pages:
            if '6a6b6ba6' in page.url:
                target = page
                break
        if not target:
            print("ERROR: conversation tab not found")
            await browser.close()
            return

        # Focus the tab
        await target.bring_to_front()
        await target.wait_for_timeout(1500)

        # Find the prompt textarea and type
        editor = target.locator('#prompt-textarea')
        await editor.click()
        await target.wait_for_timeout(500)
        await editor.fill(MESSAGE)
        await target.wait_for_timeout(500)

        # Send with Enter
        await editor.press('Enter')
        print("Message sent, waiting for reply...")
        await target.wait_for_timeout(5000)

        # Check send success (look for stop button or assistant response)
        state = await target.evaluate("""() => {
            const sendBtn = document.querySelector('button[data-testid="send-button"]');
            const stopBtn = document.querySelector('button[data-testid="stop-button"]');
            return {hasSend: !!sendBtn, hasStop: !!stopBtn, disabled: sendBtn ? sendBtn.disabled : null};
        }""")
        print(f"Send state: {state}")

        await browser.close()

asyncio.run(main())
