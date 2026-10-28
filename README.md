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
