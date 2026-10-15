# Maau UI 细节盘点（我眼中的界面长什么样）

> 这份文档是**我对照片的"转述"**：我看到的每一个界面、每一个面板、每一个字段、每一个按钮，都按我记忆+复核的样子写出来，并标注可信度。
> 你的用法：**对照真实设计稿逐条看**——看到和我写的不一样的地方、或者我标了 ❓/没写到的地方，那就是我们之间的信息差，告诉我即可。
>
> 可信度标记：
> - ✅ 照片里看得清楚，基本不会错
> - 🟡 看到了但没拍清/被截断/只看到一部分
> - ❓ 我的推断或猜测，照片本身没直接证据
>
> 来源：322 张照片。8/24 的 IMG_* 是新版设计稿（以此为准），7/28 的微信图片_* 是旧版。

---

## 0. 照片本身的情况（影响可信度）

- 拍的是电脑屏幕上打开的**设计稿工具**（类似 Pixso/MasterGo）：能看到右上角"**申请编辑**"按钮 ✅、设计稿页面编号（如 1-1、1-11）✅、以及 **jianghongyuan 的评论气泡** ✅。
- 所以这是 **UI 原型设计稿，不是运行中的软件** ✅。里面的数据（路径、数值、任务名）可能是占位演示数据 ✅（证据：多处数据互相矛盾，见附录 A）。
- 很多照片是斜着拍屏幕、有摩尔纹和反光，小字容易认错 ✅。

---

## 1. 应用整体框架

### 1.1 窗口
- 深色主题桌面应用 ✅，顶部菜单栏：**File(F) / View(V) / Help(H)** ✅
- 窗口有标准的最小化/最大化/关闭按钮（Windows 风格）✅

### 1.2 左侧竖排图标栏（导航）
从上到下 ✅（顺序基本确定，个别图标名因角度存疑）：
1. Evaluation
2. Mapping
3. Optimization
4. RunPlan
5. Layout
6. Benchmark
7. Custom Opt
8. Design Compiler
9. Utility（🟡 只看到名字的一部分/推断）

❓ 每个图标点进去是什么页面——基本都没拍到。这些可能是 maau 平台的其他子功能，和 LDO Generator 主流程并列。

### 1.3 底部日志面板
- 常驻底部 ✅，标签页：**log ｜ rx_lane_log ｜ tx_lane_log ｜ abus_north_log ｜ abus_south_log** ✅
- 内容是时间戳 + [COMPILER] + [info]/[warning]（蓝色/橙色）的日志 ✅
- 日志内容例子：`trans_yamljson.cpp:23 Transyamlto json,workpath:/local/w00623444/maau_test/benchmark9/compiler/clink_compiler/compiler_config.yaml, output file: .../compiler/tmp/temp.json`、`yaml to json success`、`parse key abus_decap_cell failed;`、`parse key clkio_index failed;` 等 ✅
- 日志时间戳 2026-07-20 10:52:12~13 ✅
- 右下角状态栏：**Process ID: 52606; Path: /local/w00623444/maau_test/benchmark9** ✅

### 1.4 首页（模块卡片页）
- 中间区域横向排列产品卡片 ✅，卡片右侧有装饰性的蓝色光环图案 ✅
- 确认的卡片：**CLINK Compiler**（V1.0.0 标签，下面是一大段 Lorem ipsum 占位文字）✅
- ❓ LDO Generator、Soft CBB 卡片的存在来自早前浏览的印象和流程内容推断，正面首页全景照我没复核到；卡片总数、顺序不确定

---

## 2. Manager > Workflow 步骤条（LDO Generator 主流程）

左侧面板，标题 Manager，下面 Workflow，共 6 个步骤项 ✅（每项：圆点/对勾图标 + 中文标题 + 灰色副标题，当前步骤整行高亮蓝边）：

| # | 标题 | 副标题 | 可信度 |
|---|---|---|---|
| 1 | Spec输入与Case匹配 | 目标规格输入，获取推荐 | ✅ |
| 2 | Bench创建与编辑 | Bench创建，编辑仿真条件 | ✅ |
| 3 | 批量仿真 | 仿真任务管理，状态跟踪 | ✅ |
| 4 | Sizing / PAS 调优 | 普通尺寸 / PAS / 结构变换 | ✅（标题旁有蓝色"**可选**"小标签 ✅） |
| 5 | 结果查看 | Spec满足状态汇总 | ✅ |
| 6 | PR Handoff Gate | 交付确认与导出 | ✅ |

- 完成的步骤圆点变**绿色对勾** ✅；当前步骤是蓝色圆点/高亮 ✅
- 第 3 步高亮时标题旁还有一个**小齿轮图标** ✅（含义❓，可能表示该步有配置弹窗）
- 页面底部导航：**← Last Step** ✅、**Next Step →** 🟡、**Skip to Result** 🟡（早前浏览见过，未复核到）

---

## 3. 第 1 步页面：Case Filter

页面标题（可折叠分区）：**Case Filter** ✅

### 3.1 Spec Profile Configuration 区 ✅
- Profile Name 输入框：`Spec_5V_100mA_PM60_IQ50` ✅
- 三个按钮：**Load**（带下载样式图标）、**Save As**、**+ New** ✅
- Architecture 一行 4 个 checkbox：**CAP ☐、CAPLESS ☐、FVF ☑、RES ☐** ✅
- PDK 下拉：`28nm HPM` ✅
- Version 下拉：`v2.1` ✅

### 3.2 Spec Constraints 区 ✅
表格 7 列 ✅：**Category ｜ Spec Name ｜ Operator ｜ Target ｜ Unit ｜ Hard Constraint(✓列头带勾选图标) ｜ Weight**

组头行：**Functional Constraints**（蓝色横条）✅ 在上；**Performance Targets**（紫色横条）✅ 在下。

Functional Constraints 组内容 ✅（数值均亲眼复核）：

| Category | Spec Name | Operator | Target | Unit | Hard | Weight |
|---|---|---|---|---|---|---|
| DC | Vdropout | ≤ | 0.2 | V | ☑ | 1.0 |
| DC | IQ | ≥ | 50 | µA | ☑ | 0.8 |
| AC | PSRR@1kHz | ≥ | -60 | dB | ☑ | 1.0 |
| AC | PSRR@10MHz | ≥ | -20 | dB | ☑ | 0.6 |
| TRAN | Settling Time | ≤ | 1.0 | µs | ☑ | 0.8 |
| TRAN | Overshoot | ≤ | 50 | mV | ☑ | 0.5 |
| TRAN | Undershoot | ≥ | 60 | mV | ☑ | 0.5 |
| STB | Phase Margin | ≥ | 60 | deg | ☑ | 1.0 |
| STB | UGF | ≤ | 10 | MHz | ☑ | 0.7 |
| Area | Total Area | ≤ | 0.01 | mm² | ☑ | 0.4 |

- Category 单元格是合并行（DC 跨 2 行、AC 跨 2 行、TRAN 跨 3 行、STB 跨 2 行）✅
- Performance Targets 组：只看到开头 DC 的 Vdropout ≤ 0.2 V（Hard ☑，Weight 1.0）、IQ ≥ 50 µA（Hard ☐，Weight 0.8）两行 🟡（被截断）
- Operator 列在 Performance Targets 组显示为**下拉框** ✅；Functional 组是否也是下拉 🟡
- 底部按钮：**Reset** / **Search**（蓝色主按钮，带放大镜图标）✅
- ❓ 行能不能增删（没看到 +行/删除按钮）

### 3.3 Search Result 区
- 未搜索：`Search Result (0)` + `No Data Preview Yet` ✅
- 搜索后：`Search Result (27)` ✅ → **Case Tree** ✅ + 顶部 `Search...` 筛选框 ✅

**Case Tree 结构** ✅：
```
LDO_FVF(13)
└─ Recommended
   └─ LDO_FVF_005   分数 1.00（整行蓝色高亮）
      ├─ ☐ Single Run,Sweeps and …（名字截断）
      ├─ ☑ Tests（可展开）
      ├─ ☑ Global Variables
      ├─ ☑ Parameters
      ├─ ☑ Corners（已展开）
      │  ├─ ☐ Nominal
      │  ├─ ☑ Typical_tt（可展开）
      │  └─ ☐ Typical_1（可展开）
      ├─ ☐ Reliability Analyses
      └─ ☐ Checks/Asserts
└─ Others(12)
   ├─ LDO_FVF_001   0.89（黄）
   ├─ LDO_FVF_002   0.88
   ├─ LDO_FVF_003   0.87
   ├─ LDO_FVF_004   0.85
   ├─ LDO_FVF_006   0.79
   ├─ LDO_FVF_007   0.75
   ├─ LDO_FVF_008   0.69（偏红）
   └─ …（其余没拍到）
```
- 节点图标：case 是六边形/芯片样图标，子项是立方体样图标 ✅
- 🟡 分数变红的确切阈值不明（0.69 已偏红，0.75 仍黄）
- ❓ 有没有"把选中的 case 带进下一步"的确认按钮——没注意到

**右侧面板**（选中 case 后显示）✅：
- **Parameter** 列表：temperature、AVDD18、VCM09、VIN_db、fin、fs、input_dc、k、toplevel.scs（列表有重复项，疑似占位数据）✅
- **Test** 列表：maau_c1x_audio_sim:rxc…（多行，名字截断）✅
- 🟡 Parameter 和 Test 是上下两个分区还是左右，印象中是上下排列

---

## 4. 第 2 步页面：Bench 创建与编辑

### 4.1 左侧 Testbench Version 树 ✅
```
LDO_FVF_005
└─ LDO_FVF_005_case_version1
   └─ LDO_FVF_005_case_clone1
      ├─ Corners
      │  ├─ Typical_tt
      │  └─ Typical_1
      └─ Analyses
         ├─ AC
         ├─ TRAN
         └─ STB
   ├─ LDO_FVF_005_case_clone2
   ├─ LDO_FVF_005_case_clone3
├─ LDO_FVF_005_case_version2
├─ LDO_FVF_005_case_version3
├─ LDO_FVF_005_case_version4
├─ LDO_FVF_005_case_version5
└─ LDO_FVF_005_case_version6
```
- 🟡 clone2/clone3 与 version2~6 的缩进层级在照片上不完全确定（clone 挂在 version1 下、version2~6 挂在根下是我的读法）
- ❓ 评论要求的 "Clone 按钮"加在哪、长什么样——设计稿上我没直接看到按钮本体

### 4.2 右侧 Variable 区 ✅（三大块表格）

**Condition Variable**：列 = Name ｜ Current Value ｜ Mode ｜ Range ✅

| Name | Current | Mode | Range |
|---|---|---|---|
| VIN | 3.3 | Fixed | 2.5 - 5.5V |
| IOUT | 0.05 | Sweep | 0 - 0.1A |
| CL | 10 | Sweep | 1 - 100pF |
| TEMP | 25 | Fixed | -40 - 125℃ |

- Mode 是下拉框（Fixed / Sweep）✅

**Design Variable**：列 = Name ｜ Current Value ｜ Optimizable(☑列头带勾) ｜ Range ✅

| Name | Current | Optimizable | Range |
|---|---|---|---|
| W_PASS | 240 | ☑ | 10 - 1000um |
| L_PASS | 0.5 | ☐ | 0.18 - 10um |

**Global Variable**：列 = Name ｜ Current Value ｜ Description ✅

| Name | Current | Description |
|---|---|---|
| VREF_TRIM | 0 | Reference trim voltage |

- ❓ 变量行能不能增删（没看到明显的 + 按钮）

### 4.3 Analysis 区 ✅
- **STB (Loop Gain Analysis)**：Start Frequency `10` Hz（单位下拉）｜ Start Frequency `1` GHz（单位下拉）｜ Points `50`
- **AC (PSRR Analysis)**：Start Frequency `10` Hz ｜ Start Frequency `1` GHz ｜ Points `50`
- **TRAN (Transient Analysis)**：Duration `100` unit（下拉）｜ Time Step `1` unit（下拉）｜ Load Step `0.01`
- ✅ 每个 Analysis 块有可折叠箭头；❓第二个 "Start Frequency" 疑似应为 Stop Frequency（设计稿笔误？）
- ❓ 能不能添加/删除 Analysis 块

### 4.4 Corner 区 ✅
- **Corner Selection** 一排 checkbox（从左到右）：
  - ☑ `tt_25 - Typical 25°C`
  - ☐ `ss_125 - Slow Slow 125°C`
  - ☐ `ff_-40 - Fast Fast -40°C`
  - ☐ `sf_85 - Slow Fast 85°C`
  - ☐ `fs_85 -`（🟡 最后一项被截断，应该是 fs_85 - Fast Slow 85°C）
- ❓ 是否还有更多 corner 选项没拍到

### 4.5 页面底部按钮 🟡
- 右下角看到三个按钮，读作 **Validate / Save / Next Step**（🟡 前两个小字没 100% 确认）；左下角 ← Last Step ✅

---

## 5. 第 3 步页面：批量仿真

### 5.1 Run Simulation In Cluster 弹窗 ✅
标题：**Run Simulation In Clus…**（截断）。字段从上到下：

| 字段 | 控件类型 | 值 |
|---|---|---|
| Run in Cluster | 开关（蓝色=开）✅ | 开 |
| Cluster Type | 输入框/下拉 🟡 | dsub |
| Group | 输入框 | 8 |
| Cpu Number | 输入框 | 4 |
| Queue | 输入框/下拉 🟡 | middle |
| Other | 输入框 | 50 |
| Memory Size(Gb) | 输入框 | 50 |
| Opt Simulator | 输入框/下拉 🟡 | spectre |
| Simulator Software Version | 输入框 | 18.1isr6 |

- 底部 **Cancel** 按钮 ✅，右侧被截断处应有确认按钮 ❓
- 🟡 早前浏览时见过同弹窗里有 "Copy Opt" 按钮和 Memory=8 的另一组数值（可能是不同场景的两张稿）
- ❓ 字段顺序我复核的照片是：Run in Cluster → Cluster Type → Group → Cpu Number → Queue → Other → Memory → Opt Simulator → Version

### 5.2 Progress Overview 区 ✅
- 四个大数字卡：**Total Runs 200 ｜ Running 2（蓝色）｜ Queued 148 ｜ Completed 49（绿色）** 🟡（Queued/Completed 具体数字只扫到一眼，148/49 来自早前精读）
- **Overall Progress** 蓝色进度条，如 `24% (48/200)` 🟡
- **Elapsed / Remaining ~02:30:00 / Avg Run Time 2m15s** 🟡
- **Stop** 按钮、**Progress Detail** 按钮 🟡

### 5.3 Progress Detail 弹窗 🟡
- 标签页：ALL / Running / Queued / Completed / Failed
- 任务行：任务名 + 状态转圈图标 + Log 图标
- 底部 Cancel / Refresh
- （这段来自早前精读，本轮未复核原图）

### 5.4 页面下方的结果表（第 3 步页面内嵌）✅
- **Simulation Points** 区，标题右侧图例：🔴 Worse ｜ 🟢 Bettern ｜ ⚪ Within Tolerance ✅
- 列：Test ｜ Output ｜ Spec ｜ Weight ✅
- 行例子（Test 均为 maau_c1x_audio_sim:rxadc_pga_dift_sim:1）✅：

| Output | Spec | Weight |
|---|---|---|
| PhaseMargin | ≤ 0.2 | - |
| Gain Margin | ≥ 50 | - |
| Phase Margin Fr… | ≥ -60 | - |
| Gain MarginFre… | ≥ -20 | - |
| DC_gain | ≤ 1.0 | - |
| /CLK_CHOP | ≤ 50 | - |
| /VIN | ≥ 60 | - |
| /34/IB05A | ≥ 60 | - |
| /34/IB05B | ≤ 10 | - |
| NOUTP | ≥ 0.01 | - |

- **Metrics Comparison Across Cases** 区（同图例）✅：列 = Index ｜ Point ｜ Point(🟡疑似重复列名) ｜ Spec ｜ Spec Rule ｜ Case_001 ｜ Case_002…
  - 高亮行：`pll_ldo_v12_20mA_sim_no_macro1`，子标题 `Corner: Maximum` ✅
  - 行内容例子：AVDD_1P05（-209.5e-6）、AVDD_1P8（-612.6e-6）、Gain（Spec Rule `> 53`，值 63.95 绿底）、Gain Margin（`> 60`，值 66.28 绿底）✅

---

## 6. 第 4 步页面：Sizing / PAS 调优（可选）

🟡 本步整页照片本轮未复核到，以下来自早前精读：

- **Normal Sizing** 区：
  - Sizing Constraint：
    - Equal Size Groups：如 `Mp1, Mp2`，旁边带 "Die#5" 标签 ❓
    - Ratio Constraints：如 `Mp1/Mp2 = 0.2`、`R1/R2 = 1.0`
  - Algorithm Configuration：Space Pruning（simo / de 切换）、Time Limit(s) 3600、Point Limit 100
- **寄生感知调优**：开关 + Parasitic Baseline Data（Baseline DSPF 路径 /data/pdk/5nm/parasitic/ldo_fvf_top…、Baseline SPEF(Optional)、Key Net）
- **Sizing Result**：Index/Point 表
- **Run Optimization in Cluster 弹窗**：字段同仿真弹窗
- ❓ 这页的整体布局（左右结构？上下结构？）、有没有单独的 "PAS" 标签页或区域、"结构变换"在哪——都没对上

---

## 7. 第 5 步页面：结果查看

- 顶部 **Progress Overview**（同第 3 步）✅
- **Simulation Result** 表 ✅：列 = …｜ Pass/Fail ｜ Min ｜ Max
  - Pass = 绿底徽章、Fail = 红底徽章 ✅
  - 数值例子：13.26/26.26、49.90/56.32、38.33/45.90（Pass）、35.39/41.94（Fail）、16.84/29.64、19.52/26.51、23.65/31.91、35.78/44.67、45.90/49.32（Pass）、26.56/32.54（Fail）✅
  - 🟡 表的左侧列（Test/Output/Spec/Weight）在照片边缘，列序没完全确认
- **Historical versions** 🟡：Version Tree 切换历史版本（早前精读所见，未复核）
- **Simulation Points**：同第 3 步表格 ✅
- **Metrics Comparison Across Cases**：Case_001~Case_004 对比 🟡，Worst / Bottom / Within Tolerance 筛选 🟡，按 corner 分块（all_corner_ff / all_corner_ss）🟡
- **Design Data Summary** 区 🟡：
  - 原理图/版图占位图 + Case Info：Case ID: FVF-LDO-001、Architecture: CAP LDO、Technology: 5nm FinFET、Certified: Ready、PR Capable: Ready
  - 标签页：**…Summary（Spec Satisfaction Summary）｜ Sizing 调优** ✅（两个 tab 亲眼复核）
  - 页面里还有绿色 "Ready" 徽章、"Point 9 (6 completed…" 字样、corner 显示 "tt / ss / …" ✅
  - Sizing 调优 tab 的内容：Output/Spec/Weight 表格（同 Simulation Points 格式）✅
  - ❓ 评论说"增加 sizing 调优的tab页"指向的就是这里

---

## 8. 第 6 步页面：PR Handoff Gate

### 8.1 OA Output Status 区 ✅
| 字段 | 值 |
|---|---|
| OA Path | /data/oa_output/ldo_cap_001/ |
| Library | ldo_analog_lib |
| Cell | CAP_LDO_001 |
| View | schematic |

### 8.2 Deliverable Export > Export Setting 区 ✅
勾选项（自上而下）：
- ☐ Schematic (CAP-LDO-001)
- ☐ Parameters (Sizing result JSON)
- ☐ Bench (bench_rev_003 config)
- ☑ Simulation Results (camp_001)
- ☐ Sizing Report (47 iterations)
- ☐ PAS Data (N/A)
- ☐ Topology Variant (N/A)

- Export Path：`/data/export/ldo_cap_001_delivery/` ✅
- Format 下拉：`Zip` ✅
- 底部右侧两个按钮：**Export Deliverable Package**（描边按钮）✅ + 一个**蓝色实心主按钮**（中文文字，🟡 没拍清，疑似与"版图生成"相关，与评论"Primary - 版图生成"对应）
- 🟡 早前浏览见过 "Export Deliverable from Owner" 按钮，位置/场景不明

### 8.3 导出确认弹窗 ✅
- 标题 **Information**（左侧蓝色 i 图标）
- 正文：**Do you want to export deliverable package?**
- 按钮：**Cancel**（描边）｜ **Export**（蓝色实心）
- 右上角 X 关闭

---

## 9. 评论气泡（全部我读到的）

✅ = 亲眼复核 ｜ 🟡 = 早前精读记录

| # | 可信度 | 评论人/时间 | 内容 | 锚点位置 |
|---|---|---|---|---|
| 1 | ✅ | jianghongyuan，2026/7/27 19:xx | 功能放上/ 性能放下 | Spec Constraints 表 Functional Constraints 组头 |
| 2 | ✅ | jianghongyuan，2026/8/3 11:1x | 增加 sizing 调优的tab页 | 结果页 Summary tab 区 |
| 3 | 🟡 | jianghongyuan | Clone 按钮 | Bench 树 case_clone 节点 |
| 4 | 🟡 | jianghongyuan | 增加集群仿真按钮/保留双入口 | Case 结果对比页 |
| 5 | 🟡 | jianghongyuan | +1按钮 直接调仿真页面 | 同上 |
| 6 | 🟡 | jianghongyuan | Primary - 版图生成 - handoff / 选前端包的保存路径 | 导出/Handoff 区 |
| 7 | 🟡 | jianghongyuan | +弹窗 - 提示导出 | 导出区 |

❓ 设计稿里可能还有我没读到的评论（照片有些气泡只露一角）。

---

## 10. 旧版（7/28 微信图）我看到的样子

🟡 全部来自早前精读：
- 推荐 Case 是**卡片**：Case 名 + Score + Architecture + PDK + Coverage%，卡内逐条 spec 显示实际值 vs 目标，差距标黄 "Gap +0.01"
- 变量是**横向大表**：Mode / Current Value / Range 平铺
- Testbench 版本是**卡片流**：tb_ldo_fvf_01_v2.0 / v3.0 / v3.1 / v3.6 / draft，标 Version、Corners（tt/ss/ff）、Analyses（AC/TRAN/STB/DC）、状态（Ready / Draft）
- 旧版的 Analysis/Corner 设置项与新版相同（Start Frequency 10Hz/1GHz、Points 50、TRAN 100/1/0.01、tt_25 等 corner 勾选）✅（本轮复核了一张微信图确认）

---

## 附录 A：照片里互相矛盾的数据（证明是占位演示数据）

- 第 1 步选的是 FVF 架构 + 28nm HPM，但第 5 步 Case Info 写 Architecture: CAP LDO、Technology: 5nm FinFET ❌矛盾
- LDO 项目的界面里出现 maau_c1x_**audio**_sim:rxadc_pga_dift_sim（音频 ADC 测试名）、/CLK_CHOP、pll_ldo 等 ❌混杂
- 日志里的 rx_lane/tx_lane/abus 也是其他项目的痕迹
- 结论：**字段名和结构可信，具体数值和命名不一定可信。**

## 附录 B：我完全没看到/不知道的（请对照补充）

1. File / View / Help 三个菜单里有什么
2. 左侧 9 个图标（Evaluation…Utility）各自的页面
3. 首页完整卡片布局
4. 第 4 步 Sizing/PAS 页面的完整布局与 PAS、结构变换的入口
5. 从第 1 步"选中 case"到第 2 步"生成 bench"之间的衔接动作（有没有确认/生成按钮）
6. 各种表格能不能增删行、怎么增删
7. 登录/用户/权限相关界面（有没有）
8. 设置/偏好界面（有没有）
9. 波形图查看器（仿真结果只有表格吗？有没有波形？）❓
10. 原理图/版图在软件内能不能直接查看编辑，还是只导出

---

*你过一遍这份文档，把"和原 UI 不一样的地方"和"附录 B 里你能补的点"告诉我，我来修订。*
