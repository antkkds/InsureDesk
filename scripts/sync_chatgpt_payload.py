"""Sync ChatGPT: full payload + error analysis request."""
import asyncio, sys
from playwright.async_api import async_playwright

MESSAGE = """[InsureDesk 项目 — GE 报价自动化：两个 portal 都测了，premium 计算成功但 Save 被服务器拒绝]

**进展更新：**
1. 确认了 GEGLink 的两个 portal：
   - Portal 1: Houseowner/Householder Quotation (houseQuote.html) — general 保单
   - Portal 2: Fire Quotation (fireQuote.html) — 火险
2. 两个 portal 的表单都填通了（动态日期解决 backdated 校验），premium 都算出来了
3. **但点 Save 都被服务器拒绝**："House quotation fail to saved" / "Fire quotation fail to saved"

**Portal 1 (houseQuote) 完整提交 payload（65 字段，关键项）：**
- houseQuote.jpj_h_q_cov_start_date = 04/08/2026
- houseQuote.jpj_h_q_cov_end_date = 04/08/2027
- houseQuote.jpj_h_q_insured_name = Fionn Liang
- houseQuote.jpj_h_q_add1/2/3 = 地址
- houseQuote.jpj_h_q_hp_ext = 012, hp_no = 3456789
- houseQuote.jpj_h_q_tp_of_bld_cd = 4001 (Dwellings - Detached)
- houseQuote.jpj_h_q_const_class_cd = 1A
- houseQuote.jpj_h_q_howner_sum_insured = 200000
- houseQuote.jpj_h_q_howner_rate = 0.106 (服务器返回的费率)
- totalOthHouseOwner = 212.00 (保费)
- houseQuote.jpj_h_q_prem_stamp_duty = 10.00
- houseQuote.jpj_h_q_prem_grand_total = 222.00 (总保费 RM222)
- saveHouseQuotation = true, houseOwnerOnly = true
- houseHolderOnly = "" (没填 householder 部分)
- radio houseQuote.jpj_h_q_hholder_lst_cnt_opt = A (All contents) 已选
- hholder_lump_sum_insured = 50000 (也填了)
- 其余 householder 字段 = 0

**Portal 2 (fireQuote) 完整提交 payload（108 字段，关键项）：**
- fire.jpj_f_q_cov_start_date = 02/08/2026, end = 01/08/2027
- fire.jpj_f_q_insured_name = Fionn Liang, add1-3 地址
- fire.jpj_f_q_hp_ext = 012, hp_no = 3456789
- fire.jpj_f_q_tp_of_bld_cd = 1001 (Dwellings)
- fire.jpj_f_q_const_class_cd = 1A
- fire.jpj_f_q_sum_in_building = 200000
- totalSumInsured = 200000.0
- fire.jpj_f_q_basic_fire_rate = 0.052, f_basic_premium = 104.0
- fire.jpj_f_q_grand_total_prem = 114.0 (总保费 RM114)
- saveFireQuotation = true

**JS 流程（两个 portal 相同逻辑）：**
- 填字段触发 change → prepData() → isValidInfo() 通过 → Ajax POST 到同页 → evalData() 计算 rate/premium → enable Save 按钮
- 点 Save → changeValue()/minOnSubmit() 设 saveXxxQuotation=true → form.submit() → 服务器返回 "xxx quotation fail to saved"

**已排除的原因：**
- ✅ 日期不 backdated（04/08/2026 是明天）
- ✅ isValidInfo 通过（无错误标记）
- ✅ premium 计算成功（服务器 Ajax 返回了 rate）
- ✅ saveXxxQuotation=true 设置了
- ✅ 表单类型标记正确（houseOwnerOnly=true）

**请你分析：服务器拒绝保存最可能的原因是什么？**
1. 还有必填业务字段没填？（比如某个隐藏字段、householder 部分、延伸险选择）
2. 保额/费率组合问题？（200000 保额 + 1A 构造 + Dwellings）
3. 服务器端 session/会话问题？（独立 Chrome 登录的会话）
4. 测试数据问题？（客户名/IC 不存在于 GE 系统？）
5. 需要人工基准：你能建议我们怎么拿到"一次成功保存的 payload"来对比吗？（比如让用户手动做一次，或检查是否有 preview/draft 功能）
6. 或者这个表单的 Save 根本不是最终提交 — 还有别的流程？（比如先 Save Draft 再 Submit？）

请给出具体的排查方向。"""

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
        await target.bring_to_front()
        await target.wait_for_timeout(1500)
        editor = target.locator('#prompt-textarea')
        await editor.click()
        await target.wait_for_timeout(500)
        await editor.fill(MESSAGE)
        await target.wait_for_timeout(500)
        await editor.press('Enter')
        print("Message sent")
        await target.wait_for_timeout(3000)
        state = await target.evaluate("""() => {
            const sendBtn = document.querySelector('button[data-testid="send-button"]');
            const stopBtn = document.querySelector('button[data-testid="stop-button"]');
            return {hasSend: !!sendBtn, hasStop: !!stopBtn};
        }""")
        print(f"Send state: {state}")
        await browser.close()

asyncio.run(main())
