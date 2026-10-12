set st_project = "/tmpdata/maau_epc/users/k00981589/st-engine-maau"
cd "$st_project"
set st_source_cds = "/tmpdata/maau_epc/users/k00981589/maau_cbb/cds.lib"

mkdir -p /tmpdata/maau_epc/users/k00981589/st-engine-maau-runs
set st_run = `mktemp -d /tmpdata/maau_epc/users/k00981589/st-engine-maau-runs/ocldo_top_XXXXXXXX`
mkdir -p "$st_run/logs" "$st_run/backend_runs"

set st_work = "$st_run/work"
set st_operations = "$st_run/test_operations"
set st_backend = "$st_project/server/st_virtuoso_backend.sh"
set st_session_cds = "$st_run/cadence/cds.lib"
set st_variant_lib = "HiAplatRV500_ldo_sim_ST_STRUCT"
set st_run_name = `basename "$st_run"`
set st_variant_id = "TS_${st_run_name}"
set st_variant_cell = "ldo1_0_cbb_top__${st_variant_id}"

setenv ST_BACKEND_RUN_ROOT "$st_run/backend_runs"
echo "本次测试目录=$st_run"
预期类似：
本次测试目录=/tmpdata/maau_epc/users/k00981589/st-engine-maau-runs/ocldo_top_Ab12Cd34
9.2 准备 Cadence 会话
bash server/prepare_session.sh --source-cds-lib "$st_source_cds" --session-dir "$st_run/cadence" --variant-lib "$st_variant_lib"
set st_rc = $status
echo "准备会话退出码=$st_rc"
预期显示本次 cadence/cds.lib 路径，以及：
准备会话退出码=0
成功后执行：
cat "$st_session_cds"
预期包含：
INCLUDE /tmpdata/maau_epc/users/k00981589/maau_cbb/cds.lib
DEFINE HiAplatRV500_ldo_sim_ST_STRUCT ...
DEFINE HiAplatRV500_ldo_sim_ST_STRUCT__STAGING ...
9.3 读取正确的电路并扫描 PDK
下面第一条是一整条命令：
python3 server/site/standalone.py inspect --validation-scope structure_only --backend "$st_backend" --cds-lib "$st_session_cds" --lib HiAplatRV500_ldo_sim --cell ldo1_0_cbb_top --view schematic --core-subckt ldo1_0_cbb_top --work-dir "$st_work" --variant-lib "$st_variant_lib" --variant-cell "$st_variant_cell" --variant-id "$st_variant_id" --skill "$st_project/skill/standalone_topology_variant.il" >& "$st_run/logs/09_inspect.log"
set st_rc = $status
tail -60 "$st_run/logs/09_inspect.log"
echo "inspect退出码=$st_rc"
预期包含：
会话已创建: .../work
可修改MOS[所选核心cell当前层]: 实际数量
原始网表: .../before/core_before.scs
inspect退出码=0
成功后检查会话记录：
grep -E '^(source_library|source_cell|source_view|core_subckt|validation_scope)=' "$st_work/session.conf"
ls -lh "$st_work/before"
预期包含：
source_library=HiAplatRV500_ldo_sim
source_cell=ldo1_0_cbb_top
source_view=schematic
core_subckt=ldo1_0_cbb_top
validation_scope=structure_only
文件列表至少包含：
core_before.scs
device_catalog.tsv
geometry.tsv
mos_inventory.tsv
本次只处理所选原理图当前层的 MOS。若 MOS 数量为 0，先停止，把第 9 步输出发来。
10. 自动准备电阻和 Stack 测试操作
python3 server/site/prepare_structure_test.py --session "$st_work" --output "$st_operations"
set st_rc = $status
echo "准备操作退出码=$st_rc"
预期类似：
RESISTOR_TARGET=实际实例名
STACK_TARGET=另一个实际实例名
RESISTOR_MASTER=实际扫描到的电阻master
CDF_RANGE_KNOWN=true或false
STRUCTURE_TEST_PREPARED files=4
准备操作退出码=0
程序会自动选两个不同的当前层标量 MOS，准备四个操作文件。
成功后查看：
cat "$st_operations/test_selection.json"
ls -lh "$st_operations"
预期有：
resistor_initial.conf
resistor_changed.conf
stack_two.conf
stack_three.conf
test_selection.json
如果出现 STOP，停止。固定流程需要至少两个不同标量 MOS 和一个可用真实电阻。
11. 确认第一版：Source 串电阻＋两级 Stack
先确认电阻：
python3 server/site/standalone.py confirm --session "$st_work" --operation "$st_operations/resistor_initial.conf"
set st_rc = $status
echo "确认初始电阻退出码=$st_rc"
预期：退出码 0，当前操作数为 1。
再确认 Stack：
python3 server/site/standalone.py confirm --session "$st_work" --operation "$st_operations/stack_two.conf"
set st_rc = $status
echo "确认两级Stack退出码=$st_rc"
python3 server/site/standalone.py list --session "$st_work"
预期：退出码 0，列表显示：
已确认操作: 2
并列出电阻和 Stack 两项操作。
12. 连续撤回两次
第一次撤回 Stack：
python3 server/site/standalone.py undo --session "$st_work"
set st_rc = $status
echo "撤回Stack退出码=$st_rc"
python3 server/site/standalone.py list --session "$st_work"
预期：退出码 0，剩余 1 项电阻操作。
第二次撤回电阻：
python3 server/site/standalone.py undo --session "$st_work"
set st_rc = $status
echo "撤回电阻退出码=$st_rc"
python3 server/site/standalone.py list --session "$st_work"
预期：退出码 0，剩余操作数为 0。
13. 修改阻值，并改为三级 Stack
python3 server/site/standalone.py confirm --session "$st_work" --operation "$st_operations/resistor_changed.conf"
set st_rc = $status
echo "确认新阻值退出码=$st_rc"
预期：退出码 0，操作数为 1。
继续：
python3 server/site/standalone.py confirm --session "$st_work" --operation "$st_operations/stack_three.conf"
set st_rc = $status
echo "确认三级Stack退出码=$st_rc"
python3 server/site/standalone.py list --session "$st_work"
预期：退出码 0，最终操作数为 2。
两次阻值的实际数值见第 10 步的 test_selection.json。
14. 测试恢复初始逻辑结构
python3 server/site/standalone.py fresh --session "$st_work"
set st_rc = $status
echo "fresh退出码=$st_rc"
python3 server/site/standalone.py list --session "$st_work"
预期包含：
已恢复到初始逻辑结构，活动操作数=0
fresh退出码=0
列表显示操作数 0。
15. 重新确认最终两项操作
python3 server/site/standalone.py confirm --session "$st_work" --operation "$st_operations/resistor_changed.conf"
set st_rc = $status
echo "最终电阻确认退出码=$st_rc"
退出码为 0 后继续：
python3 server/site/standalone.py confirm --session "$st_work" --operation "$st_operations/stack_three.conf"
set st_rc = $status
echo "最终Stack确认退出码=$st_rc"
python3 server/site/standalone.py list --session "$st_work"
预期：两个退出码均为 0，最终操作数为 2。
16. 生成派生原理图并执行回读校验
python3 server/site/standalone.py generate --session "$st_work" >& "$st_run/logs/16_generate.log"
set st_rc = $status
tail -80 "$st_run/logs/16_generate.log"
echo "generate退出码=$st_rc"
预期包含：
validation_scope=structure_only
structural_ready=true
nominal_dc_ready=false
pvt_ready=false
parameters_quantized=false
ready_for_sizing=false
封装子Cell数=2
generate退出码=0
派生电路应位于：
HiAplatRV500_ldo_sim_ST_STRUCT/本次派生Cell名称/schematic
这是结构验收，DC、PVT 和性能尚未验证；上述三个就绪标志为 false 是本流程的预期结果。
17. 检查验证报告和源图
cat "$st_work/reports/validation.txt"
预期报告包含：
ok=true
structural_ready=true
stage=complete
generated_cells=2
validation_scope=structure_only
source=HiAplatRV500_ldo_sim/ldo1_0_cbb_top/schematic
然后检查源图网表：
cmp "$st_work/before/core_before.scs" "$st_work/after/source_roundtrip.scs"
set st_rc = $status
echo "源图未改检查退出码=$st_rc"
预期：cmp 没有输出，随后显示：
源图未改检查退出码=0
18. 检查正式发布库
下面第二条是一整条命令：
setenv ST_VALIDATION_SCOPE structure_only
"$st_backend" netlist --cds-lib "$st_session_cds" --lib "$st_variant_lib" --cell "$st_variant_cell" --view schematic --core-subckt ldo1_0_cbb_top --output "$st_run/final_root.scs" --device-policy "$st_work/analysis/device_policy.tsv" >& "$st_run/logs/18_final_root.log"
set st_rc = $status
tail -20 "$st_run/logs/18_final_root.log"
echo "正式库回读退出码=$st_rc"
预期：
正式库回读退出码=0
成功后执行：
python3 -c 'from pathlib import Path; import sys; s=Path(sys.argv[1]).read_text(); assert "__STAGING" not in s, "正式根图仍依赖STAGING"; print("FINAL_ROOT_NO_STAGING_DEPENDENCY")' "$st_run/final_root.scs"
set st_rc = $status
echo "暂存依赖检查退出码=$st_rc"
预期：
FINAL_ROOT_NO_STAGING_DEPENDENCY
暂存依赖检查退出码=0
19. 在 Virtuoso 打开最终原理图
前面报告、源图比较和正式库检查全部成功后执行：
python3 server/site/standalone.py open --session "$st_work"
set st_rc = $status
echo "open退出码=$st_rc"
echo "最终原理图=$st_variant_lib/$st_variant_cell/schematic"
echo "测试证据目录=$st_run"
预期包含：
已请求打开：HiAplatRV500_ldo_sim_ST_STRUCT/本次派生Cell名称/schematic
open退出码=0
