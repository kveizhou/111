# Maau 平台功能说明书（通俗版）

> 这份文档用大白话讲清楚 Maau 这个软件是干什么的、每个界面每个选项是什么意思。
> 写给**没用过这个软件、也不懂模拟电路**的人看。
> 文中所有 ❓ 标记的地方，是我从照片上看不出来、或者理解不了的点，需要你问懂的人之后补充。
> 信息来源：322 张 UI 设计稿照片（不是真实运行的软件，是设计工具里的原型图）。

---

## 〇、先花两分钟了解背景（不懂模拟电路也能看懂）

**这个软件一句话概括：**
> 帮芯片工程师"自动设计并调好一个 LDO 电路"的工具。你告诉它"我要一个什么样性能的电路"，它从库里找最接近的现成方案，自动跑大量仿真测试，自动调参数，最后打包交付。

**必须认识的几个词（后面会反复出现）：**

| 词 | 大白话解释 |
|---|---|
| **LDO** | 一种电源芯片电路，作用是把不稳定的输入电压变成稳定干净的输出电压（比如把 5V 变成稳当的 3.3V 给芯片内部用）。就像"电压的稳压器"。 |
| **Spec（规格）** | 你要的电路必须达到的指标清单。比如"输出波动不能超过 0.2V"、"耗电不能超过 50µA"。就像点外卖时写的"少辣、不要香菜、30 分钟内送到"。 |
| **Case（用例/方案）** | 案例库里一个现成的电路设计方案，自带完整的测试配置。这个软件的核心思路是"不从头设计，而是找最接近的现成方案来改"。 |
| **Bench / Testbench（测试台）** | 一套"考试装置"：规定好在什么条件下（电压、温度、负载……）对电路做哪些测试。 |
| **仿真（Simulation）** | 用电脑软件（这里是 Cadence 公司的 spectre 仿真器）模拟电路运行，不用真的造出芯片就知道它的性能。一次仿真就像"做一遍模拟考"。 |
| **Corner（工艺角）** | 芯片制造有误差、温度会变化。Corner 就是"在最坏/最好/典型的制造与温度条件下分别考试"。比如 tt_25 = 典型工艺+25°C，ss_125 = 最慢工艺+125°C（高温恶劣条件）。 |
| **Sizing（调尺寸）** | 电路里晶体管的"宽和长"（W/L）直接决定性能。Sizing 就是自动调整这些尺寸参数，让性能达标。可以类比"调收音机的旋钮直到声音最清楚"。 |
| **PAS** | ❓ 没搞懂。从界面看它和"寄生感知调优""结构变换"一起出现，猜测是某种考虑版图寄生效应的高级调优方式，或者某种电路结构变换技术。**需要问人确认。** |
| **寄生 / Parasitic** | 电路画成版图（实际芯片的布线图纸）后，走线本身会带来额外的电阻电容，叫寄生效应，会让实际性能变差。"寄生感知调优"就是调参数时提前把这些影响算进去。 |
| **PDK** | 芯片制造工艺的"规则包"，比如"28nm HPM"代表台积电 28 纳米高性能工艺。设计电路必须基于某个 PDK。 |
| **OA / OA库** | Cadence Virtuoso（画电路图和版图的软件）的数据库格式。导出的电路最终要放进 OA 库给别人用。 |
| **PR Handoff** | PR = Physical Design Review 或 Project Release（❓不确定是哪个），总之是"把关卡"：确认所有指标合格，把设计资料打包交给下游团队。 |
| **集群仿真（Run in Cluster）** | 一次测试可能要跑几百个仿真（不同温度×电压×工艺组合），一台电脑跑太慢，就提交到公司的服务器集群上并行跑。dsub 是集群任务提交工具。 |

---

## 一、软件整体长什么样

这是一个**深色主题的桌面软件**（像 VS Code 那种深色界面），内部名叫 maau。整个界面分五大块：

```
┌──────────────────────────────────────────────────────────┐
│  顶部菜单栏： File(F)   View(V)   Help(H)                  │
├────┬─────────────────────────────────────────────────────┤
│ 左 │                                                      │
│ 侧 │              中间：主工作区                            │
│ 竖 │      （显示当前步骤的页面/首页的模块卡片）              │
│ 排 │                                                      │
│ 图 │                                                      │
│ 标 │                                                      │
│ 栏 │                                                      │
│    ├─────────────────────────────────────────────────────┤
│    │  底部：日志面板（log / rx_lane_log / tx_lane_log /     │
│    │  abus_north_log / abus_south_log 五个标签页）         │
├────┴─────────────────────────────────────────────────────┤
│  右下角状态栏： Process ID: 52606   Path: /local/.../benchmark9 │
└──────────────────────────────────────────────────────────┘
```

**左侧竖排图标栏**（从上到下）：Evaluation、Mapping、Optimization、RunPlan、Layout、Benchmark、Custom Opt、Design Compiler、Utility。
❓ 这些图标分别对应什么功能页面，照片里大部分只看到了图标和名字，内容页没拍到或还没设计。从名字猜：Evaluation=评估、Mapping=映射、Optimization=优化、RunPlan=运行计划、Layout=版图、Benchmark=基准测试、Custom Opt=自定义优化、Design Compiler=设计编译器、Utility=工具。

**底部日志面板**：一直显示，有 5 个标签页（log、rx_lane_log、tx_lane_log、abus_north_log、abus_south_log）。里面滚动的是 COMPILER 模块的运行日志，能看到 yaml 配置文件转 json、"parse key xxx failed"（解析某个配置项失败）之类的信息。日志时间戳是 2026-07-20。
❓ rx_lane / tx_lane / abus_north / abus_south 这些日志名看起来来自另一个芯片项目（像是高速接口/SerDes 相关），为什么 LDO 工具的日志页签是这些名字，需要问人。

**首页**：中间是模块卡片，一张卡片一个产品。拍到的有 **CLINK Compiler**（V1.0.0）等卡片，卡片上是占位文字（Lorem ipsum，说明介绍文案还没写）。核心的 **LDO Generator** 是主要模块，另有 **Soft CBB** 模块，还有空白占位卡片预留将来扩展。
❓ 首页一共有几张卡片、各自的名字和顺序，没有一张完整的正面照片，我只能确认 CLINK Compiler、LDO Generator、Soft CBB 这三个名字。

---

## 二、核心流程：六步向导（Manager > Workflow）

进入 LDO Generator 后，左边出现一个 **Workflow（工作流程）步骤条**，一共 6 步，每步有中文标题+副标题，做完一步会打绿色对勾：

| 步骤 | 标题 | 副标题 | 通俗解释 |
|---|---|---|---|
| 1 | Spec输入与Case匹配 | 目标规格输入，获取推荐 | 告诉软件你要什么 → 它推荐现成方案 |
| 2 | Bench创建与编辑 | Bench创建，编辑仿真条件 | 搭好"考试装置"，设置考试条件 |
| 3 | 批量仿真 | 仿真任务管理，状态跟踪 | 把几百场"模拟考"扔到服务器集群上跑 |
| 4 | Sizing / PAS 调优 | 普通尺寸 / PAS / 结构变换（标了"**可选**"蓝标签） | 如果成绩不达标，自动调晶体管尺寸再试 |
| 5 | 结果查看 | Spec满足状态汇总 | 看成绩单：哪些指标过了、哪些没过 |
| 6 | PR Handoff Gate | 交付确认与导出 | 确认没问题，打包交付给下游 |

页面底部有 **← Last Step（上一步）** / **Next Step（下一步）** / **Skip to Result（跳到结果）** 按钮，可以前进后退。
❓ "Skip to Result" 出现的条件和行为没拍清楚——是不是任何时候都能直接跳到第 5 步？

下面逐步展开。

---

## 三、第 1 步：Spec输入与Case匹配（页面名：Case Filter）

**这一步在干嘛：** 你像填"需求表"一样填电路指标，点 Search，软件从案例库里找出和你需求最接近的现成 Case，按匹配度打分排序。

页面分上下两大块：

### 3.1 Spec Profile Configuration（规格档案配置）

| 界面元素 | 是什么 | 照片里看到的例子 |
|---|---|---|
| Profile Name | 这份规格档案的名字，可以存起来下次直接用 | `Spec_5V_100mA_PM60_IQ50`（含义大概是：5V 输入、100mA 电流、相位裕度 60、静态电流 50） |
| Load 按钮 | 载入以前存过的规格档案 | |
| Save As 按钮 | 把当前填的另存为一个档案 | |
| + New 按钮 | 新建空白档案 | |
| Architecture（多选框） | 电路的拓扑结构类型，四个选项：CAP / CAPLESS / FVF / RES | 例子里勾了 FVF |
| PDK（下拉框） | 用哪个制造工艺 | `28nm HPM` |
| Version（下拉框） | PDK 或工艺库的版本 | `v2.1` |

❓ Architecture 四个选项的准确含义：CAP（带片外电容的 LDO）、CAPLESS（无片外电容的 LDO）、FVF（Flipped Voltage Follower，一种电路结构）基本能确定；**RES 是什么不确定**（可能是某种电阻反馈结构？）。
❓ Architecture 能不能多选？例子里只勾了一个，但用的是方框勾选（checkbox）而不是单选圆点，理论上能多选。

### 3.2 Spec Constraints（规格约束表）

一张大表格，每行是一条性能指标。表头共 7 列：

| 列名 | 含义 |
|---|---|
| Category | 指标类别：DC（直流/静态指标）、AC（交流/频率指标）、TRAN（瞬态/响应速度指标）、STB（稳定性指标）、Area（面积指标） |
| Spec Name | 指标名称 |
| Operator | 比较符：≤（不超过）或 ≥（不低于），下拉框可选 |
| Target | 目标值 |
| Unit | 单位（V、µA、dB、µs、mV、deg、MHz、mm²） |
| Hard Constraint ✓ | 勾选框：这条是不是"硬指标"。硬指标 = 必须满足，不满足就一票否决；不勾 = 尽量满足的"软指标" |
| Weight | 权重（0.4~1.0 的数字）：这条指标在综合打分时占多大份量 |

**表格分两大组**（这是评论里专门要求改的："功能放上/性能放下"）：

**第一组：Functional Constraints（功能约束，蓝色组头，在上面）** —— 电路"能不能正常工作"的底线指标：

| Category | Spec Name | Operator | Target | Unit | 权重示例 |
|---|---|---|---|---|---|
| DC | Vdropout（压差：输入至少要比输出高多少） | ≤ | 0.2 | V | 1.0 |
| DC | IQ（静态电流：电路自己待机吃多少电） | ≥ | 50 | µA | 0.8 |
| AC | PSRR@1kHz（低频电源抑制比：抗输入纹波能力） | ≥ | -60 | dB | 1.0 |
| AC | PSRR@10MHz（高频电源抑制比） | ≥ | -20 | dB | 0.6 |
| TRAN | Settling Time（稳定时间：负载突变后多久稳住） | ≤ | 1.0 | µs | 0.8 |
| TRAN | Overshoot（过冲：瞬间冲高多少） | ≤ | 50 | mV | 0.5 |
| TRAN | Undershoot（下冲：瞬间跌多少） | ≥ | 60 | mV | 0.5 |
| STB | Phase Margin（相位裕度：电路稳不稳、会不会振荡） | ≥ | 60 | deg | 1.0 |
| STB | UGF（单位增益带宽） | ≤ | 10 | MHz | 0.7 |
| Area | Total Area（电路总面积） | ≤ | 0.01 | mm² | 0.4 |

**第二组：Performance Targets（性能目标，紫色组头，在下面）** —— 格式同上的另一组指标（照片里只露了开头 DC 的 Vdropout、IQ 两行，被滚动条截断了）。

❓ 两组指标的区别我只能从名字推测："Functional Constraints"是必须满足的功能底线，"Performance Targets"是争取达到的加分项。但例子里两组都有 Hard Constraint 勾选框，**两组的实际区别和用途需要问人**。
❓ IQ 那里 Operator 是 ≥（静态电流"大于等于 50µA"），按电路常识 IQ 一般是"越小越好"，应该是 ≤。这可能是设计稿填错了，也可能我理解错了指标定义，需要确认。
❓ Undershoot ≥ 60mV 同理（下冲居然要求"大于等于"），存疑。

表格右下角两个按钮：**Reset（重置）** / **Search（搜索）**。

### 3.3 Search Result (N)（搜索结果区）

没搜索前显示 "Search Result (0) / No Data Preview Yet"。搜索后（例子里是 27 个结果）变成：

**Case Tree（案例树）**：
- 顶部有个 Search... 搜索框（在结果里再筛选）
- 结果按架构分组，比如 `LDO_FVF(13)` = FVF 架构下有 13 个 Case
- 组内分两档：
  - **Recommended（推荐）**：匹配分最高的，如 `LDO_FVF_005`，右侧分数 **1.00**（满分），整行蓝色高亮
  - **Others(12)（其他候选）**：按分数从高到低排——0.89、0.88、0.87、0.85、0.79、0.75、0.69……分数高的是黄色数字，低到 0.69 左右变成**红色**数字
- 每个 Case 可以展开，里面是这个方案自带的配置项，**每项前面有勾选框**（可以选要不要）：
  - ☐ Single Run, Sweeps and …（单次运行/扫描设置，名字被截断）
  - ☑ Tests（测试项）
  - ☑ Global Variables（全局变量）
  - ☑ Parameters（参数）
  - ☑ Corners（工艺角，可再展开：☐ Nominal、☑ Typical_tt、☐ Typical_1）
  - ☐ Reliability Analyses（可靠性分析）
  - ☐ Checks/Asserts（检查/断言）

**右侧面板**：选中某个 Case 后，右边显示它的详细内容：
- **Parameter 列表**：temperature、AVDD18、VCM09、VIN_db、fin、fs、input_dc、k、toplevel.scs 等
- **Test 列表**：maau_c1x_audio_sim:rxadc… 之类的测试名

❓ 匹配分（1.00 / 0.89…）具体怎么算出来的，界面上看不出（可能和 Hard Constraint 满足情况 + Weight 加权有关，但只是猜测）。
❓ 勾选 Case 树里的子项（比如只勾 Typical_tt 这个 corner）会影响后面的什么？猜测是"把这个 case 的部分配置带进下一步的 Bench"，需要确认。
❓ 右侧 Parameter 列表里的内容（AVDD18、VCM09、rxadc…）看起来像是**音频 ADC 项目**的参数，和 LDO 对不上，怀疑设计稿里填了别的项目的占位数据。

---

## 四、第 2 步：Bench创建与编辑

**这一步在干嘛：** 选好 Case 后，软件基于它生成一个"测试台"（Bench），你在这里设定考试条件（用什么电压、什么温度、测哪些项目）。可以存多个版本、可以复制（clone）一个版本改一改再对比。

### 4.1 左边：Testbench Version（测试台版本树）

一棵树，例子里的结构：

```
LDO_FVF_005（最顶层，对应第1步选的Case）
└─ LDO_FVF_005_case_version1
   └─ LDO_FVF_005_case_clone1        ← 从 version1 克隆出来的副本
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
├─ ...version3 / version4 / version5 / version6
```

- **版本（version）**：一份完整的 Bench 配置，可以存在多个版本（version1~6），方便对比"哪版配置测出来效果好"。
- **克隆（clone）**：复制一个版本来改，不动原版。评论里明确要求在 case 节点上加一个 **Clone 按钮**。
- 每个 clone 下面挂着自己的 Corners（考试用哪几种工艺/温度条件）和 Analyses（做哪几种分析：AC 交流、TRAN 瞬态、STB 稳定性）。

❓ version 和 clone 的区别和层级关系（为什么 clone 挂在 version1 下面，而 clone2/clone3 和 version2 又是平级？）树的展开规则没完全看懂，需要确认。

### 4.2 右边：Variable（变量面板）

变量分三类，每类一张表：

**① Condition Variable（条件变量）—— "考试环境"**

| Name | Current Value（当前值） | Mode（模式） | Range（范围） |
|---|---|---|---|
| VIN（输入电压） | 3.3 | Fixed（固定） | 2.5 ~ 5.5V |
| IOUT（输出电流/负载） | 0.05 | Sweep（扫描） | 0 ~ 0.1A |
| CL（负载电容） | 10 | Sweep（扫描） | 1 ~ 100pF |
| TEMP（温度） | 25 | Fixed（固定） | -40 ~ 125℃ |

- **Mode = Fixed**：考试时就固定用这个值。
- **Mode = Sweep**：在 Range 范围内取一串值各考一遍（比如 IOUT 从 0 到 0.1A 扫一遍，看电路在不同负载下的表现）。这就是为什么仿真会有几百个——条件组合起来的。

**② Design Variable（设计变量）—— "被调的旋钮"**

| Name | Current Value | Optimizable | Range |
|---|---|---|---|
| W_PASS（功率管宽度） | 240 | ☑ 勾选 | 10 ~ 1000µm |
| L_PASS（功率管长度） | 0.5 | ☐ 没勾 | 0.18 ~ 10µm |

- 这些是电路里晶体管的尺寸参数，是第 4 步"调优"要自动调整的旋钮。
- **Optimizable 勾选** = 允许优化器自动调这个参数；不勾 = 固定不动。
- W_PASS/L_PASS 里的 PASS 指 LDO 里的"功率传输管"（pass transistor），是 LDO 最关键的器件。

**③ Global Variable（全局变量）**

| Name | Current Value | Description |
|---|---|---|
| VREF_TRIM | 0 | Reference trim voltage（基准电压微调） |

❓ Global Variable 和 Condition Variable 的界线：VREF_TRIM 为什么算全局而不是条件？猜是"跨所有 case 共享、一般不动"的参数，需确认。

### 4.3 Analysis（分析设置）—— "考哪几科、每科考多久"

照片里看到三种分析，每种有自己的参数：

| 分析 | 参数 | 例子 |
|---|---|---|
| STB (Loop Gain Analysis) 稳定性分析 | Start Frequency / Start Frequency / Points | 10 Hz、1 GHz、50 个点 |
| AC (PSRR Analysis) 交流分析 | 同上 | 10 Hz、1 GHz、50 |
| TRAN (Transient Analysis) 瞬态分析 | Duration / Time Step / Load Step | 100、1、0.01（单位是下拉框，例子里显示"unit"） |

❓ 页面上连续两行都叫 "Start Frequency"（一个 10 Hz、一个 1 GHz），第二个十有八九应该是 "Stop Frequency"（终止频率）——很可能是设计稿的笔误，需要确认。
❓ TRAN 的单位下拉显示 "unit"，说明真实单位（µs/ns？）没填进设计稿。

### 4.4 Corner（工艺角选择）

一排勾选框，选"在哪些制造/温度条件下考试"：

- ☑ **tt_25 - Typical 25°C**（典型工艺 + 25度常温）
- ☐ **ss_125 - Slow Slow 125°C**（最慢工艺 + 125度高温，恶劣条件）
- ☐ **ff_-40 - Fast Fast -40°C**（最快工艺 + 零下40度）
- ☐ **sf_85 - Slow Fast 85°C**
- ☐ **fs_85 - Fast Slow 85°C**

（tt/ss/ff/sf/fs 是制造工艺波动的五种典型情形，不用深究，理解为"五种体质的芯片"即可。）

页面右下角还有 **Validate（校验）** / **Save（保存）** / **Next Step（下一步）** 按钮。

---

## 五、第 3 步：批量仿真

**这一步在干嘛：** 把配置好的几百个仿真任务（条件×工艺角×分析的组合，例子里是 200 个）提交到服务器集群跑，并盯进度。

### 5.1 "Run Simulation In Cluster" 弹窗（提交仿真）

点运行后弹出，配置集群资源：

| 选项 | 含义 | 例子 |
|---|---|---|
| Run in Cluster | 总开关：是否在集群上跑（关掉可能=本机跑） | 开 |
| Cluster Type | 集群任务系统类型 | dsub |
| Group | 任务分组/并行组数 ❓ | 8 |
| Cpu Number | 每个任务用几个 CPU 核 | 4 |
| Queue | 提交到集群的哪个队列 | middle |
| Other | ❓ 不知道是什么，值是 50 | 50 |
| Memory Size(Gb) | 每个任务申请的内存 | 50（另一张图里像是 8，可能不同任务不同配置） |
| Opt Simulator | 用哪个仿真器 | spectre |
| Simulator Software Version | 仿真器版本 | 18.1isr6 |

弹窗底部有 Cancel（右侧被截断，应该还有 OK/确认）。早前照片里还见过一个 **Copy Opt** 按钮 ❓（作用不明，可能是"复制上次配置"）。

❓ "Other" 字段是什么完全没头绪，需要问人。
❓ 评论里提到"保留双入口"（结果对比页也能发起集群仿真）和"+1按钮直接调仿真页面"，说明除了这一步的正常入口，第 5 步结果页还会有快捷入口。

### 5.2 Progress Overview（进度总览）

四个大数字卡片 + 进度条：

- **Total Runs 200**（总任务数）
- **Running 2**（正在跑）
- **Queued 148**（排队中）
- **Completed 49**（已完成）
- **Overall Progress** 进度条，如 24% (48/200)
- **Elapsed / Remaining ~02:30:00**（已用时间/预计剩余约 2 个半小时）
- **Avg Run Time 2m15s**（平均每个任务耗时）
- **Stop** 按钮（全部停止）、**Progress Detail** 按钮（看明细）

### 5.3 Progress Detail 弹窗（任务明细）

- 标签页：**ALL / Running / Queued / Completed / Failed**（按状态过滤）
- 任务列表：每行一个任务（名字如 maau_c1x_audio_sim:rxadc…_dift_sim:1），带状态图标（运行中转圈）和一个 **Log 图标**（点开看那个任务的日志）
- 底部 Cancel / Refresh

### 5.4 这一步页面下方还直接带着结果表格

（从照片看，批量仿真页面下方已经能看到两个结果表的雏形）

- **Simulation Points** 表：列 = Test / Output / Spec / Weight。图例有三种颜色标记：**Worse（红，比规格差）/ Bettern（绿，比规格好）/ Within Tolerance（灰，在容差内）**。行例子：PhaseMargin ≤ 0.2、Gain Margin ≥ 50、DC_gain ≤ 1.0、/CLK_CHOP ≤ 50、/VIN ≥ 60、NOUTP ≥ 0.01 等。
- **Metrics Comparison Across Cases** 表：不同 Case 之间横向对比，列 = Point / Spec / Spec Rule / Case_001 / Case_002…，达标的格子填绿色。

❓ "Bettern" 应该是 "Better" 的笔误（设计稿原文就写成 Bettern）。
❓ Simulation Points 表里 Weight 列大多显示 "-"，什么时候有值不清楚。

---

## 六、第 4 步：Sizing / PAS 调优（可选）

**这一步在干嘛：** 如果仿真结果不达标，让优化算法自动调"设计变量"（晶体管尺寸），反复仿真逼近目标。标注了"可选"——如果第 3 步结果已经全过，可以跳过。

### 6.1 Normal Sizing（普通调尺寸）

**Sizing Constraint（调尺寸约束）：**
- **Equal Size Groups（等尺寸组）**：指定几个器件必须保持一样大，如 `Mp1, Mp2`（旁边还带一个 "Die#5" 的芯片标签 ❓ 含义不明）
- **Ratio Constraints（比例约束）**：指定器件尺寸的比例关系，如 `Mp1/Mp2 = 0.2`、`R1/R2 = 1.0`

**Algorithm Configuration（算法配置）：**
- **Space Pruning（搜索空间剪枝）**：simo / de 两种模式切换 ❓（simo 可能=单输入多输出优化策略，de 可能=差分进化算法 Differential Evolution，需要确认）
- **Time Limit(s)**：最长跑多久，例子 3600 秒（1 小时）
- **Point Limit**：最多尝试多少个参数点，例子 100

### 6.2 寄生感知调优（开关）

打开后要填 **Parasitic Baseline Data（寄生基准数据）**：
- **Baseline DSPF**：/data/pdk/5nm/parasitic/ldo_fvf_top…（一个基准寄生参数文件路径）
- **Baseline SPEF (Optional)**：可选的另一个寄生文件
- **Key Net**：data1_name_keynet_1\… ❓（"关键网络"，大概是重点关注的信号线，具体格式不明）

（DSPF/SPEF 是描述版图寄生电阻电容的标准文件格式。这一步的意思大概是：调尺寸时参考已有版图的寄生数据，让仿真更接近实际芯片。）

### 6.3 Sizing Result（调优结果）

Index / Point 表格，记录优化过程试过的点，如 `pll_ldo_v12_20mA_sim_no_macro1`，标注 Corner: Maximum。

### 6.4 "Run Optimization in Cluster" 弹窗

和第 3 步的集群弹窗几乎一样（Run in Cluster 开关、dsub、middle、Memory 50、Group 8、Cpu 4、Other 50）——优化也要大量仿真，所以也能扔到集群跑。

❓ "PAS 调优"在这个页面里具体是哪一块？副标题写"普通尺寸 / PAS / 结构变换"，但我在页面上只明确看到 Normal Sizing 和寄生感知调优两块，**PAS 和结构变换的入口/界面没有对应上**，需要问人。
❓ 优化完成后怎么把结果"采纳"回设计（有没有 Apply 按钮之类）没拍到。

---

## 七、第 5 步：结果查看

**这一步在干嘛：** 汇总所有仿真成绩，看哪些指标过了、哪些挂了，还能跨 Case/跨版本对比。

包含这些区域：

1. **Progress Overview**：和第 3 步一样的进度数字。
2. **Simulation Result 表**：列 = Spec Name / Output / Spec / Weight / **Pass/Fail**（绿色 Pass 徽章、红色 Fail 徽章）/ Min / Max。比如某指标 Min 13.26、Max 26.26。一眼看出哪行挂了。
3. **Historical versions（历史版本）**：Version Tree（和左边 Bench 版本树呼应），切换看不同历史版本的结果。
4. **Simulation Points**：Test → Output 的明细表（同第 3 步那个表）。
5. **Metrics Comparison Across Cases**：Case_001~Case_004 横向对比表；可按 Worst / Bottom / Within Tolerance 筛选 ❓（Worst 和 Bottom 的区别不明）；按 corner 分块（all_corner_ff / all_corner_ss）；单元格数值、达标填绿。
6. **Design Data Summary**：
   - 上面是原理图/版图的占位图 + **Case Info**：Case ID: FVF-LDO-001、Architecture: CAP LDO、Technology: 5nm FinFET、Certified: Ready、PR Capable: Ready
   - 下面两个标签页：**Spec Satisfaction Summary（规格满足度汇总）** ｜ **Sizing 调优**（这个 tab 是评论要求新加的；内容是 Output/Spec/Weight 表格）

❓ Case Info 里 "Certified: Ready" 和 "PR Capable: Ready" 的确切含义和判定逻辑不明（大概是"这个设计是否已具备交付条件"的标志位）。
❓ 例子里 Architecture 写 CAP LDO、Technology 写 5nm FinFET，和第 1 步的 FVF + 28nm 对不上——再次说明设计稿填的是演示占位数据，别当真。

---

## 八、第 6 步：PR Handoff Gate（交付确认与导出）

**这一步在干嘛：** 最后一关。确认设计数据已经写进 OA 库，勾选要交付的资料，导出成压缩包交给下游。

### 8.1 OA Output Status（OA 输出状态）

| 字段 | 例子 |
|---|---|
| OA Path | /data/oa_output/ldo_cap_001/ |
| Library | ldo_analog_lib |
| Cell | CAP_LDO_001 |
| View | schematic |

（意思是：设计好的电路图已经存到了 OA 库的 ldo_analog_lib / CAP_LDO_001 / schematic 这个位置。）

### 8.2 Deliverable Export > Export Setting（交付物勾选清单）

勾选要打包的内容：

- ☐ **Schematic (CAP-LDO-001)** —— 电路原理图
- ☐ **Parameters (Sizing result JSON)** —— 调优后的参数（JSON 文件）
- ☐ **Bench (bench_rev_003 config)** —— 测试台配置
- ☑ **Simulation Results (camp_001)** —— 仿真结果
- ☐ **Sizing Report (47 iterations)** —— 调优报告（共 47 轮迭代）
- ☐ **PAS Data (N/A)** —— PAS 数据（此项不可用）
- ☐ **Topology Variant (N/A)** —— 拓扑变体（此项不可用）

下面还有：
- **Export Path**：/data/export/ldo_cap_001_delivery/（导出到哪）
- **Format**：Zip（打包格式下拉框）
- 底部两个按钮：**Export Deliverable Package**（导出交付包）和一个蓝色主按钮（中文，照片没拍清，疑似"继续生成版图"之类 ❓——评论里说过"Primary = 版图生成"，即这个主按钮应该是去生成版图）

### 8.3 导出确认弹窗

点导出后弹：**"Information — Do you want to export deliverable package?"**，按钮 Cancel / Export。（这也是评论要求的"加提示弹窗"。）

❓ "Export Deliverable from Owner" 按钮在早前照片里见过一次，和这个页面的关系不明。
❓ "选前端包的保存路径"（评论要求）在新版里对应哪个控件没对上——可能就是 Export Path 输入框，需确认。

---

## 九、评论里已定下的修改点汇总

设计稿上有同事（jianghongyuan，7/27~8/3）留的评论气泡，等于已经提好的修改需求：

| # | 位置 | 评论原文 | 通俗解释 |
|---|---|---|---|
| 1 | 第 1 步约束表 | 功能放上/ 性能放下 | 功能约束组放上面、性能目标组放下面（新版已改好） |
| 2 | 第 2 步版本树 | Clone 按钮 | case 节点上要加"克隆"按钮 |
| 3 | 第 5 步结果汇总 | 增加 sizing 调优的tab页 | 结果汇总区加一个" Sizing 调优"标签页（新版已加） |
| 4 | 结果对比页 | 增加集群仿真按钮/保留双入口 | 结果页也能直接发起集群仿真，和第 3 步的入口并存 |
| 5 | 结果对比页 | +1按钮 直接调仿真页面 | 加个"+1"按钮，一键跳到仿真页 ❓（"+1"确切指什么不明，可能是"再加一轮/再加一个点"） |
| 6 | 第 6 步导出区 | Primary - 版图生成 - handoff / 选前端包的保存路径 | 主按钮是"版图生成"；交付时要能选前端包的保存路径 |
| 7 | 第 6 步导出区 | +弹窗 - 提示导出 | 导出前弹确认提示（已有雏形） |

❓ 可能还有没拍全的评论气泡，如果你在原稿里看到上面没有的评论，告诉我。

---

## 十、两个版本的区别（为什么会看到两种界面）

照片是两批：7/28 拍的（微信图片，旧版）和 8/24 拍的（IMG，新版）。**以 8/24 新版为准。** 主要差别：

| 内容 | 旧版（7/28） | 新版（8/24） |
|---|---|---|
| 推荐 Case 展示 | 卡片式：每张卡显示 Score、Architecture、PDK、Coverage%，逐条 spec 显示实际值 vs 目标，差距标黄 "Gap +0.01" | 树状 Case Tree + 匹配分（Recommended / Others） |
| 变量编辑 | 横向大表平铺（Mode/Current Value/Range 一行行） | 右侧分块面板（三类变量 + Analysis + Corner） |
| Bench 版本 | 卡片流（tb_ldo_fvf_01_v2.0 等，标 Ready/Draft） | 版本树 + clone 层级 |
| 流程导航 | 没有明显步骤条 | 左侧 6 步 Workflow 步骤条 |
| 集群/进度/对比/导出 | 没有 | 新增集群弹窗、Progress Detail、Metrics 对比、PR Handoff 导出 |

---

## 十一、我完全不懂 / 需要问人的点（汇总清单）

按重要性排：

1. **PAS 到底是什么？**（出现在：步骤 4 标题、PAS Data 导出项、PAS Sizing。猜：寄生感知调优或某种结构变换技术）
2. **"结构变换 / Topology Variant"是什么？** 什么时候会有数据（导出项里显示 N/A）
3. **集群弹窗里的 "Other" 字段是什么意思？**"Group" 的确切含义？
4. **Functional Constraints 和 Performance Targets 两组约束的实际区别？**（都有 Hard Constraint 勾选，那分组的意义是什么）
5. **Spec 表里几处反常识的运算符**：IQ ≥ 50µA（静态电流一般不超多少吗？）、Undershoot ≥ 60mV。是设计稿填错还是我理解错？
6. **Case 匹配分怎么算的？** Recommended 和 Others 的分档规则？
7. **Case 树里勾选/取消勾选子项（Tests、Corners 等）会影响后续什么？**
8. **Bench 版本树里 version 和 clone 的层级规则？**
9. **Analysis 里两个 "Start Frequency" 是不是第二个应为 Stop Frequency？**
10. **simo / de 两种 Space Pruning 模式分别是什么算法？**
11. **Key Net 的格式和作用？**
12. **"+1 按钮"的确切功能？**
13. **蓝色主按钮（第 6 步）的文字和跳转目标？**
14. **左侧图标栏 9 个图标（Evaluation…Utility）各自对应的页面内容？**（大部分没拍到）
15. **底部日志的 rx_lane / tx_lane / abus 标签页为什么是这个项目的？**
16. **设计稿里的演示数据（maau_c1x_audio_sim、5nm FinFET、pll_ldo 等）和 LDO 案例混杂**，哪些是真实字段名、哪些只是占位，需要辨别。
17. **"Export Deliverable from Owner" 按钮是什么场景用的？**
18. **Corner 选择里 ss/ff/sf/fs 的实际配置由谁定义**（用户自定义还是 PDK 自带）？

---

*文档结束。问完人之后把答案告诉我，我来更新这份文档。*
