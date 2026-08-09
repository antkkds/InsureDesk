# GEARS eQuotation Product Map (探索中 - 2026-08-XX)
SSO: geglink -> redirectJSP.html (channelType=IFE) -> POST gears-my.greateasterngeneral.com/MY/AgencySales/P
入口: /MY/AgencySales/quotations/introduce -> Select Product

## 产品分类
- Health
- Personal Accident
- Motor Insurance
- Travel Insurance
(旧系统 geglink/geglink/xxx.html: houseQuote 已记录)

## Health 流程 (4步: Coverage details -> Plans -> Details -> Payment)
### Step 1 Coverage details
- Applicant type: Individual | Corporate
- Coverage type: Family | Individual
- Main insured:
  - proposalFullname: Full name (as in NRIC/Passport)
  - proposalIdType: autocomplete (NRIC/Passport/Other)
  - proposalIdNumber: ID number
  - occupation: Occupation
  - occupation_class: Occupation class (autocomplete, e.g. Class 01)
  - proposalDOB: Date of birth (bsdatepicker, DD MMM YYYY)
  - proposalNation: Nationality (autocomplete, e.g. Malaysia)
  - Gender: Male/Female radio
  - proposalEmail: Email
  - Height/Weight
  - proposalPostalCode, proposalStateApplicant (autocomplete), proposalCountryApplicant (autocomplete), proposalAddressLine1-4
### Step 2 Plans (产品计划)
- Easi HealthCare Cashless
- Easi HealthCare Reimbursement
- EasiMed Major Cashless
- EasiMed Active Cashless
- EasiMed Active Reimbursement
- GREAT Med Care Cashless
### 弹窗
- CFF dialog: Import existing CFF / Upload hard-copy CFF / Ok
- Email PDS & DPN dialog: Ok
- Select product to compare: 多选计划 + Continue

## 交互要点 (Angular)
- 字段用 id 定位最可靠 (label 匹配会错位)
- autocomplete: focus -> type -> 等 mat-option -> click
- 按钮被模态对话框遮挡时用 JS click + 立即关对话框
- DOB: bsdatepicker 直接输入 "01 JAN 1990" 格式

### Health Plans 详情 (Easi HealthCare Cashless 选中后)
| Plan | Term | Deductible | Room | Annual Limit | Lifetime | Premium |
|------|------|-----------|------|-------------|----------|---------|
| EC300 Easi HealthCare Cashless | Until 85 | 2.5K/5K/7.5K/10K | RM300/day | RM150K | RM600K | RM1,770 |
| EM300 EasiMed Major Cashless | Until 100 | RM15K | RM300/day | RM100K | Unlimited | RM289 |
| GX300 GREAT Med Care Cashless | Until 85 | RM500 mand + opts | RM300/day | RM200K | Unlimited | RM1,930 |

### Health 探索结论 (2026-08-XX)
- 流程: Coverage details -> Plans -> Details -> Payment
- CFF 对话框是硬性必填 (Ok button disabled 直到导入已有 CFF 或上传 CFF 文件, max 20mb JPG/PNG/PDF)
- 选择产品: .plans-detail-select 行内 mat-checkbox (必须 Playwright 原生 click, JS el.click() 无效)
- 计划选择: #plan-btn-EC300 / EM300 / GX300
- 未完成: Step3 Details, Step4 Payment (需真实 CFF 数据)

## Personal Accident 流程 (4步, 无 CFF 卡点)
### 产品列表 (8个): Easi Protector PA, EasiShield PA, GreatShield Active, Great Ride Shield, Junior Protector, Lady Protector, Classic PA, Great Shield Care, Great Shield Special
### 入口: introduce/product-list?id=PA -> hover .item_product -> 点 .content-hover .btn-primary Get quote
### Step 1 Coverage details (字段有 id!)
- Coverage type: Individual radio
- #start-date / #end-date: Coverage period (bsdatepicker, DD MMM YYYY)
- #occupation, #occupation_class, #birthday
- Vehicle Indicator: Yes/No radio
### Step 2 Plans - Easi Protector (EP):
| Benefit | EP1 | EP2 | EP3 | EP4 |
| Accidental Death | 50K | 50K | 100K | 100K |
| Perm Disablement | 50K | 50K | 100K | 100K |
| Medical Expenses | 3K | 3K | 4K | 4K |
| Bereavement | 2K | 2K | 2.5K | 2.5K |
| Personal Liability | 50K | 50K | 75K | 75K |
| Ambulance | 200 | 200 | 200 | 200 |
| Premium | 160 | 114 | 229 | 171 |

## Motor Insurance 流程 (4步: Quotation Details -> Details -> Sum Insured/Add-on -> Payment)
### 产品列表 (3个): Private Motor Insurance (Private Car), Motor Commercial Vehicle, GREAT EV
### 入口: introduce/product-list?id=PMOT -> hover .item_product -> Get quote
### Step 1 Quotation details (id 定位):
- Individual/Corporate radio
- #condition: autocomplete 但初始 disabled -> 需 removeAttribute('disabled') + fill + 原生点 mat-option (NEW REGISTERED / USED 等)
- #idType: 同上 (NRIC/Passport)
- #idNumber, #sstNumber (opt), #vehicleNumber, #place (autocomplete state)
- 注意: JS el.click() 选 mat-option 不更新 Angular 模型, 必须 Playwright 原生 click
### Step 2 Details (字段清单):
- Owner: ID number, Salutation, Full name, Gender, DOB, Nationality, Marital status, Years driving exp, Mobile, Home(opt), Email, Email PDS/DPN 声明勾选, Mailing address (Postcode/State/Country/Addr1-4)
- Vehicle: Vehicle number, Vehicle indicator, Coverage type, Body type, Chassis no, Engine no, Engine capacity, Make, Model, Use of vehicle, Seating capacity, Year of manufacture, Place of use, Market value + Check, NVIC, NCD transfer from, NCD% + Check, CUE code, CUE value, Claims past 2 yrs, Period of insurance, Coverage duration
- Additional: Anti-Theft device, Safety feature, Garage, Hire purchase Yes/No, Named drivers (2 free, 3rd +RM10, All Driver +RM20)

## Travel Insurance 流程 (4步: Trip details -> Plans -> Details -> Payment)
### 产品列表 (2个): Travel For More+ Annual, Travel For More+ Short Term
### 入口: introduce/product-list?id=TRAV
### Step 1 Trip details:
- Trip type radio (Annual Multi Trip, per trip 120 days max)
- #start-date / #end-date (bsdatepicker)
- Select area: radio Worldwide and/or Domestic (默认)
- Coverage type radio: Insured Only / Insured + Spouse / Family
- 声明 checkbox: 马来西亚公民/PR/工作准证 + 出发前购买; <14天购买 Trip Cancellation 不赔
### Step 2 Plans - Travel For More+ Annual:
- Plan A: RM282 / Plan B: RM447 / Plan C with COVID-19: RM638
- Per traveller counter (- 0 +)
- 保障: A. Travel PA, B. Medical and Other Expenses, C. Emergency Medical Evacuation (AAN), D. Travel Inconveniences + Optional Cover (71-80不适用)

## GEGLink FORMS 完整清单 (所有 general insurance 类型)

### Claim Checklist Forms (PDF)
All Risks, Burglary, Contractor's All Risks/Erection, Equipment, Fidelity Guarantee, Fire/Houseowners/Householder, Great Tenang PA-AEFI, Marine, Medical, Money Insurance, Motor OD, Third Party Guarantor

### Engineering (9)
Boiler & Pressure Vessel, Civil Engineering Completed Risks, Contractors All Risks, Deterioration of Stock in Cold Storage, Electronic Equipment, Erection All Risks, Loss of Profits Following Machinery Breakdown, Machinery, Storage Tank Installation

### Fire (2)
FIRE INSURANCE PROPOSAL FORM, HOUSEOWNER HOUSEHOLDER PROPOSAL FORM (= houseQuote 旧系统对应)

### Foreign Worker (4)
FWCS, Workmen's Compensation, Foreign Workers Hospitalization & Surgical (SKHPPA), Foreign Workers Immigration Insurance Guarantee

### Hospitalization & Surgical (7)
EASI HEALTH-SME Part A/B, EasiMed Active, GREAT Med Care, Group Hospitalisation & Surgical, Personal Health Declaration, Easi Healthcare, EasiMed Major

### Liability (19)
CGL, Carriers & Warehousemen, D&O, Employers Liability, E&O, Food Stall, Medical Malpractice, No-Fault Clinical Trials, Non-Profit Org, Product Liability, PI for Life Agents (x2), PI Accountants/Lawyers, PI Miscellaneous, PI Architects/Engineers/Surveyors, PI Real Estate, PI Tour & Travel, PI MAISCA, Public & Product Liability, Public Liability

### Miscellaneous (3)
EASI-GOLF, EASI-HOME CONTENTS, GOODS-IN TRANSIT

### PA (4)
PERSONAL ACCIDENT, PLATINUM PA, ENHANCED COMPREHENSIVE PA, TRAVEL FOR MORE

### Marine (1)
MARINE CARGO

## Claim 探索结论
- MAKE A CLAIM 页面只有标题 "Claim Enquiry and Submission"，无在线提交链接
- Claim 通过各险种 Claim Checklist Forms (PDF) + 线下/邮件/FLAS 提交
- FLAS 链接: w1.financial-link.com.my/Agency/loginOAC.jsp
- 待确认: Claim 在线提交是否在其他系统

## eQS (portal2) 系统 — 商业险完整目录 (90 项)
入口: agent_home iframe → redirectJSP.html POST channelType=EQ → eQuotation/eQuotationLogin.aspx → Common/Dashboard.aspx
菜单: Authority Limit Check (New/Search), Search eCover Note, Dashboard, Sign Off
New Authority Limit Check = eUW_AuthorityLimitCheck.aspx (RadMenu: hover 'Authority Limit Check' → click 'New Authority Limit Check')

### Property (22)
FIR Fire Insurance | FCL Fire Consequential Losses | FCR Growing Trees | FIA Industrial All Risk | CBU Burglary | CFG Fidelity Guarantee | CMY Money | CPG Plate Glass | CAP Personal All Risk | CGH Prize Indemnity | CAM Equipment All Risk | CEQ Equipment Mobile | CGT Goods In Transit | CAE Equipment All Risk Movable | FOC OCBC Policy | CEB EASI-BIZ | CHC HOME CONTENTS | CSB Safe Deposit Box | CAC Combined All Risks | CEG Easi-Golf | CSM SMI Protector

### Bond (3)
BGT Performance | BGT Tender | BFW Bond Foreign Workers

### Engineering (11)
EBE Boiler | ECE Civil Engineering Completed Risk | ECR Contractor's All Risk | ECP Contractor's Plant & Machinery | EDS Deterioration of Stock | EEI Electronic Equipment | EER Erection All Risk | EAL Loss of Profit Machinery Breakdown | EMB Machinery Breakdown | EML MB+LOP | EST Storage Tank

### Marine (8)
MAH Marine Hull | MOC Marine Open Cover | MAC Marine Cargo | MAV Aircraft | MOG Oil & Gas | MMC Marine Certificate | MMI Marine Mortgagee Interests | MST Marine Single Transit

### GPA (3)
PEG Group Easi Shield | PAG Group Personal Accident | PSG Group Student PA

### Liability (25)
LBL Bailee's | LCG CGL Annual/Project | LEL Employer's | LPR Product | LPL Public Premises/Project | LWC Workmen's Comp Annual/Project | LDO D&O Private/Public/Non-Profit | LPI PI (AES/SPPI/Lawyers/Lawyers Excess/Misc/JMB/IT) | LPP Public Personal | LFS Food Stall | LEO E&O JMB | LHM Hospital Malpractice | LLA Life Agent | LAA Aerial Airport

### EasiBiz (3)
FFS Standard | FFP Premier | FEF Flexi

### 其他
- Transaction Type: New Business / Renewal
- Construction class: 1A Brickwork/Concrete+Concrete/Metal roofs, 1B Partly brickwork...
- 表单字段: Urgency, Class(ddlProduct), Transaction Type(ddlTransactionType), Proposer/Insured, Postcode, Address, State, City, Email, Phone, Policy Effective/Expiry, Risk Description, Sum Insured, Premium, Highest SI, Co-Inward Y/N, Distribution Channel, Agent, Marketeer, Description, Upload Docs (.tif .doc .docx .xls .xlsx .pdf)
- houseQuote (Fire) 就在此系统 — 之前直连 houseQuote.html 失败因未先走 eQS SSO
