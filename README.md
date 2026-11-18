Cascode／MOS 结构变换修改评审与移植说明
一、任务目标
请评审随附的 ldo_st_2_changes.zip，并将其中仍然适用的修改移植到服务器上的最新完整代码。
重要：压缩包基于较旧代码制作，不允许直接整文件覆盖最新版本。
请逐文件、逐代码块比较，保留最新版本已有功能和接口；相同能力已经存在时优先复用，避免重复实现。压缩包用于说明实现方式和算法，不代表可以直接合入。
本轮包含三项原始需求，以及一项对 VBIAS 的最新修正。最新要求优先，旧的“3 MOS＋2 电阻、32 次搜索”方案必须废弃。
二、功能要求
1. 阵列 MOS／pcell 必须作为整体变换
对于扫描得到的下列实例：
Text

复制
I0/I36/I82[29:0]
I0/I36/I82<29:0>
I82[7]
这些 pcell 在 Virtuoso 中表现为一个 MOS，因此必须作为一个完整 MOS 处理，不得展开成各个 bit，也不得只修改其中一个 bit。
需要支持四种操作：
同型 Cascode；
异型 Cascode；
源极串电阻；
MOS Stack。
变换后应保持整个阵列范围、参数和端子连接的一致性。新增 Cascode、复制管和 VBIAS 电阻也应继承相同的阵列范围，不能出现标量器件与阵列器件混接。
2. 根据真实工艺 CDF 决定尺寸输入方式
进入页面前，应根据当前 PDK 器件的真实 CDF 参数映射，判断 MOS 使用：
W/L；或
WF/NF/L。
页面、service、CLI 和最终参数写入必须保持同一种模式：
W/L 工艺显示并修改宽度、长度；
WF/NF/L 工艺显示并修改单指宽度、指数目、长度；
不得向只接受 WF/NF/L 的器件强行写入 W；
尺寸覆盖统一经过 ApplyCustomMosParameters，完成真实 CDF 映射、范围检查和量化；
同型 Cascode 保持复制原管参数，异型 Cascode 按目标器件 CDF 做合法映射，不得直接套用不存在的参数名。
三、VBIAS 最新要求：严格一只 MOS＋一只电阻
同型和异型 Cascode 共用此原则。
VBIAS 模板中只允许：
一只复制原管的 MOS；
一只偏置电阻 R_BIAS。
不得再生成镜像 MOS、镜像输出管、参考电阻或二极管连接的 Cascode Replica。
连接方式：
复制管 Gate 接原管 Gate，即 VG_CTRL；
复制管 Source 输出 VBIAS；
R_BIAS 从 VBIAS 接回原管 Source，即 VS_ORIG；
NMOS 复制管 Drain 接 VHIGH；
PMOS 复制管 Drain 接 VLOW；
Bulk／Well 沿用现有 PDK 规则；
阵列目标保持相同阵列范围。
模板应严格包含两个器件。即使伪造 solved.ok=true，旧五器件模板也不能绕过变换门禁。
四、电阻初值和 DC 调整算法
电阻初值使用原管基线 DC 工作点：
Text

复制
R0 = abs(initial_vds) / abs(initial_current)
其中 initial_vds 优先使用 intrinsic VDS，initial_current 使用原管 ID；参数非法、电流接近零或工作点缺失时，不得开始搜索。
每个候选 R 都必须：
按真实电阻 CDF 约束量化；
重建完整 Cascode＋VBIAS 候选电路；
调用宿主 DC；
读取真实 OP 后判断工作区；
根据结果决定下一次 R。
调阻方向：
NMOS 原管饱和裕量不足：增大 R；
NMOS 新增 Cascode 饱和不足，但原管工作区正确：减小 R；
PMOS 方向相反；
原管原来在线性区时，按相反方向调节，使原管及复制管尽量保持原来的线性区，不能擅自改成饱和区。
当调整方向反转时建立 bracket，后续候选取上下界的几何中点。量化后候选重复、触及阻值边界或无可行窗口时应停止并报告失败。
最多执行 20 次调 R 的名义 DC。
基线 DC 和选中 R 后的固定参数 PVT 复验单独计数，不占用这 20 次名义搜索额度。
接受候选前至少检查：
DC 收敛且快照完整；
原管保持基线工作区；
复制管保持基线工作区；
新增 Cascode 必须饱和；
VBIAS 电压范围合理；
支路电流方向和主支路连续性；
MOS 可靠性限值；
R_BIAS 电压、电流、功耗及额定值。
宿主执行失败、OP 读取失败或快照不完整时立即停止，不得继续将其解释为“电气无解”。DC 不收敛才允许尝试下一个 R。20 次内没有可行解必须返回失败，不得用 best_effort 或结构生成成功冒充电气成功。
五、重点审查的实现位置
请优先对照以下模块，不要依赖旧版本行号：
AutoBias.cpp、st/AutoBias.h
两器件 VBIAS 模板、器件选型、复制管参数继承。
ResistanceBiasSolver.cc、st/ResistanceBiasSolver.h
R0、调阻方向、量化去重、bracket、20 次名义 DC 上限及完整候选构建。
DcSolver.cpp、st/DcSolver.h
原管／复制管／新增 Cascode 的 OP 检查、VBIAS、电流及可靠性约束。VBIAS 应读取复制管 Source，不再读取旧镜像支路节点。
Transform.cpp
ApplyCustomMosParameters、阵列整体 Cascode、两器件 VBIAS 门禁。
Cli.cpp
最终封装角色绑定只能包含复制管和 R_BIAS，不能再要求 P_REF/N_REF/P_OUT/N_OUT/R_REF。
Materialization.cpp
最终 staging 和 PVT 的电阻 OP、应力检查只针对实际存在的 R_BIAS。
GUI、service、CDF／OP 提取相关文件
检查阵列身份、W/L 与 WF/NF/L 页面参数，以及真实 OP 提取链路是否完整。
六、需要服务器补充的验证
随附代码只完成了算法回归、假宿主测试和部分后端语法检查，不等于真实 Spectre 验证，也没有完成私有 service／Qt 的整机编译。
请在完整环境中完成：
最新代码移植后的全量编译，包括 service、CLI、Qt 页面和后端；
原有测试及随附回归测试；
NMOS／PMOS、同型／异型 Cascode；
标量 MOS、单下标 MOS、[29:0] 阵列 pcell；
W/L 和 WF/NF/L 两类真实工艺；
R0 首次成功、原管工作区失败后调整成功、新增 Cascode 饱和不足后调整成功；
原线性区保持线性、20 次耗尽失败、宿主错误立即停止；
旧五器件模板被拒绝；
真实 Virtuoso／Spectre DC，并附上原管、复制管和新增 Cascode 的 OP 证据；
最终 OA 回读、参数、阵列范围、端子连接及 PVT 复验。
当前自动 VBIAS 的真实候选求解仅支持 DUT 根层 MOS。嵌套层级目标应明确报“不支持”，不能静默生成未经 DC 验证的结构；如需支持嵌套层级，请另行设计并验证。
七、请返回的评审结果
请提供：
按严重程度排序的代码评审问题；
与最新代码的冲突及具体移植方式；
实际修改文件清单和差异摘要；
全量编译、测试及真实 DC 的执行日志；
仍未验证的功能和限制。
不要为了让测试通过而伪造 OP、放宽工作区判据，或把“结构生成成功”作为“电气求解成功”。














为我修改代码，共三个点，然后将修改的文件整体打包发给我：1️⃣之前我没有处理过扫出来的如I0/I36/I82[29:0]这种pcell，现在需要将其整体当作一个mos来可以进行四种结构变换操作，这些pcell在virtuoso里面看起来也是一个mos。2️⃣有的工艺是不能直接修改w,是接受两个参数wf,nf，所以进入页面前分析工艺是接受wf,nf,l还是w,l，然后将页面改为对应的。3️⃣对于同型异型cascode功能，将vbias改为一个原管mos下面加一个电阻，然后仿真分析原管和新增管是否在正确的原来工作区，不在就调整R再次仿真，这里怎么调整你要确定，包括R的初值。


请将 GitHub 仓库中的结构变换修复，完整合入当前服务器的主流程代码。

参考仓库：
https://github.com/kveizhou/LDO_ST

原始导入版本：
1c9e29405e6917857346815299314db59f5bddec

本次目标版本：
74aa33f90890120953da8838499fc7a5734fe9cf

这期间有三次修改：
1. 4130c0c：按真实 OA 实例层级物化，并从生成后的顶层回读验证。
2. 4952781：从指定 DUT 扫描全部 MOS，补充逐层扫描和定位日志。
3. 74aa33f：当前结构变换运行链的 Python 调度迁移到 C++，修正撤销、恢复初始、输出命名和预览刷新。

请先读取目标版本的 SERVER_HANDOFF.md，然后查看完整差异：

git diff --name-status 1c9e294 74aa33f
git diff --stat 1c9e294 74aa33f
git diff 1c9e294 74aa33f -- circuit_platform opt_algo

实施要求：
1. 对照服务器现有代码，确认哪些修改已经合入，只补齐缺失部分。
2. 将参考仓库 circuit_platform/、opt_algo/ 下的相对路径映射到服务器对应工程。
3. 按 Git 差异处理全部 A（新增）、M（修改）、D（删除），不能只覆盖已有文件。
4. 保留服务器已有的其他主流程功能。遇到代码冲突，结合调用关系合并，不用参考仓库覆盖整个工程。
5. 最新提交新增的关键生产文件包括：
   circuit_platform/src/modules/st_engine/NativeSkillBackend.cpp
   circuit_platform/src/modules/st_engine/st/NativeSkillBackend.h
   circuit_platform/src/modules/st_engine/st/GeneratedHistory.h
   并删除：
   opt_algo/common/structure_transform/st_virtuoso_backend.py
   同时迁移其原有调用者，检查是否仍有残留引用。
   完整文件清单以累计 Git diff 为准。
6. 检查新增 C++ 文件是否进入实际构建目标，沿用主流程的 CMake、JSON、集群和 Virtuoso 接口。重新配置并编译真实主工程。
7. 仅实现这些提交对应的功能，不新增备份、容灾、安全加固或额外框架。

需要保持的行为：
- 从实际 DUT 开始，扫描本层 MOS，同时递归所有子模块。
- 保留电路层级；封装放在目标 MOS 所在模块内。
- 只有生成并回读成功，才添加“已修改”标记。
- 撤销恢复上一份成功结果，被撤销 MOS 可再次修改。
- 恢复初始清空修改和标记，回到原 DUT。
- 每次生成使用独立 Cell 名；输出目录明确，cds.lib 保留原库定义。
- 运行日志包含实际 DUT、层级路径、命令、退出码及 Cadence 日志位置。

验收：
扫描 → 修改深层 MOS A → 修改另一层 MOS B → 撤销 B
→ 再改 B → 恢复初始 → 再改 A → 生成最终电路。

请实际编译，并明确报告：
- 已新增、修改、删除哪些文件；
- 编译是否通过；
- 哪些真实 Virtuoso 测试通过、哪些尚未执行；
- 是否还有运行时 Python 调用及其位置。

注意：参考版本当前整合入口是结构生成和 OA 回读，
并不包含原型中的候选 DC 搜索、名义 DC 和 PVT 流程。
若服务器已经有这些功能，请保留，不得因合入参考版本而删除。
