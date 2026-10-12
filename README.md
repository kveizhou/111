/tmpdata/maau_epc/users/k00981589/
保留文件名，然后逐条执行：
cd /tmpdata/maau_epc/users/k00981589
set st_zip = "/tmpdata/maau_epc/users/k00981589/LDO服务器测试包_物化日志完整保留_2026-10-10.zip"
ls -lh "$st_zip"
unzip -tq "$st_zip"
set st_rc = $status
echo "压缩包检查退出码=$st_rc"
预期包含：
No errors detected ...
压缩包检查退出码=0
2. 备份旧工具目录，再解压
先执行：
set st_stamp = `date +%Y%m%d_%H%M%S`
if (-d st-engine-maau) mv st-engine-maau "st-engine-maau_backup_${st_stamp}"
set st_rc = $status
echo "旧目录处理退出码=$st_rc"
预期：
旧目录处理退出码=0
如果原来存在 st-engine-maau，它现在保存在：
st-engine-maau_backup_实际日期时间
退出码为 0 后再执行：
unzip -q "$st_zip"
set st_rc = $status
echo "解压退出码=$st_rc"
ls -ld st-engine-maau
预期：
解压退出码=0
并显示新解压的 st-engine-maau 目录。
3. 设置本次路径，创建新测试目录
逐条执行：
set st_project = "/tmpdata/maau_epc/users/k00981589/st-engine-maau"
cd "$st_project"
pwd
预期：
/tmpdata/maau_epc/users/k00981589/st-engine-maau
然后执行：
set st_source_cds = "/tmpdata/maau_epc/users/k00981589/maau_cbb/cds.lib"
ls -lh "$st_source_cds"
python3 --version
预期：
- 显示新仓库的 cds.lib。
- Python 为 3.8 或更高版本。
接着创建本次测试目录：
mkdir -p /tmpdata/maau_epc/users/k00981589/st-engine-maau-runs
set st_run = `mktemp -d /tmpdata/maau_epc/users/k00981589/st-engine-maau-runs/ocldo_newrepo_XXXXXXXX`
mkdir -p "$st_run/logs" "$st_run/backend_runs"

set st_work = "$st_run/work"
set st_operations = "$st_run/test_operations"
set st_backend = "$st_project/server/st_virtuoso_backend.sh"
set st_session_cds = "$st_run/cadence/cds.lib"
set st_variant_lib = "HiAplat730RV200_Maau_cal_ST_STRUCT"
set st_run_name = `basename "$st_run"`
set st_variant_id = "TS_${st_run_name}"
set st_variant_cell = "ocldo18to12_200ma_core__${st_variant_id}"

echo "本次测试目录=$st_run"
预期类似：
本次测试目录=/tmpdata/maau_epc/users/k00981589/st-engine-maau-runs/ocldo_newrepo_Ab12Cd34
随机字符以实际输出为准，后续变量会自动沿用。
检查源码：
python3 -c 'from pathlib import Path; import sys; sys.path.insert(0,"scripts"); from server_test_interactive import check_source; check_source(Path.cwd())'
set st_rc = $status
echo "源码核对退出码=$st_rc"
预期包含：
已核对本次源码文件：180
源码核对退出码=0
4. 编译工具
unsetenv ST_BUILD_DIR
unsetenv ST_BUILD_MAAU_COMPAT
unsetenv ST_BUILD_MAAU_ADAPTER

bash scripts/build.sh >& "$st_run/logs/04_build.log"
set st_rc = $status
tail -20 "$st_run/logs/04_build.log"
echo "build退出码=$st_rc"
预期末尾包含：
built: /tmpdata/maau_epc/users/k00981589/st-engine-maau/build/bin/st_circuit_tool
tests: /tmpdata/maau_epc/users/k00981589/st-engine-maau/build/tests
build退出码=0
编译期间输出写入日志，等命令结束再执行后面的查看命令。
5. 执行完整回归测试
先清除旧的后端运行目录设置：
unsetenv ST_BACKEND_RUN_ROOT
bash scripts/test.sh >& "$st_run/logs/05_tests.log"
set st_rc = $status
tail -40 "$st_run/logs/05_tests.log"
echo "test退出码=$st_rc"
本包预期末尾包含：
test programs passed: 19
demos passed: 2
cli help passed: 1
server backend contract passed: 1
shell syntax checks passed: 18
standalone PDK entry and signed OP tests passed: 20
source-bound PDK discovery tests passed: 11
structure-only entry and fixed workflow tests passed: 9
read-only terminal diagnostic dispatch tests passed: 6
CDF terminal native check preparation and dispatch tests passed: 3
PDK candidate policy preparation, dispatch and logging tests passed: 5
CDF round-trip diagnostic selection and dispatch tests passed: 6
test退出码=0
这些是工具回归测试；新仓库的真实电路读取在第 9 步执行。
6. 执行输入辅助测试
python3 tests/ServerTestInteractiveTest.py >& "$st_run/logs/06_input_tests.log"
set st_rc = $status
tail -30 "$st_run/logs/06_input_tests.log"
echo "输入辅助测试退出码=$st_rc"
预期包含：
Ran 8 tests
OK
输入辅助测试退出码=0
7. 加载 Cadence 环境
逐条执行：
unsetenv ST_SKILL_INIT
unsetenv ST_PDK_TECH_ADAPTER
unsetenv ST_SITE_INPUTS_MANIFEST
unsetenv ST_SITE_CASE_CONTEXT
unsetenv ST_CIRCUIT_CONTEXT
unsetenv ST_SIMULATION_PROFILE
unsetenv ST_PDK_METADATA
unsetenv ST_OP_PROVIDER_BIN
unsetenv ST_VALIDATION_SCOPE

source server/setup_backend.csh "$st_project"
set st_rc = $status
echo "环境加载退出码=$st_rc"
rehash
bash -c 'command -v virtuoso'
setenv ST_BACKEND_RUN_ROOT "$st_run/backend_runs"
预期包含：
st-engine-maau backend environment ready
环境加载退出码=0
并显示实际 Virtuoso 入口，例如：
/software/hicad/usage/bin/virtuoso
8. 准备新 Cadence 会话
下面第一条是一整条命令：
bash server/prepare_session.sh --source-cds-lib "$st_source_cds" --session-dir "$st_run/cadence" --variant-lib "$st_variant_lib"
set st_rc = $status
echo "准备会话退出码=$st_rc"
预期显示本次会话的 cds.lib 路径，以及：
准备会话退出码=0
成功后检查：
cat "$st_session_cds"
预期包含：
INCLUDE /tmpdata/maau_epc/users/k00981589/maau_cbb/cds.lib
DEFINE HiAplat730RV200_Maau_cal_ST_STRUCT ...
DEFINE HiAplat730RV200_Maau_cal_ST_STRUCT__STAGING ...
... 是本次新测试目录下的实际路径。
9. 读取指定电路，自动扫描 PDK
操作对象固定为：
HiAplat730RV200_Maau_cal/ocldo18to12_200ma_core/schematic
下面第一条是一整条命令：
python3 server/site/standalone.py inspect --validation-scope structure_only --backend "$st_backend" --cds-lib "$st_session_cds" --lib HiAplat730RV200_Maau_cal --cell ocldo18to12_200ma_core --view schematic --core-subckt ocldo18to12_200ma_core --work-dir "$st_work" --variant-lib "$st_variant_lib" --variant-cell "$st_variant_cell" --variant-id "$st_variant_id" --skill "$st_project/skill/standalone_topology_variant.il" >& "$st_run/logs/09_inspect.log"
set st_rc = $status
tail -60 "$st_run/logs/09_inspect.log"
echo "inspect退出码=$st_rc"
第一条运行时可能没有终端输出，因为输出写入日志。等它结束，再执行后面三条。
预期包含：
会话已创建: .../work
可修改MOS[所选核心cell当前层]: 实际数量
原始网表: .../before/core_before.scs
inspect退出码=0
MOS 数量以新仓库实际结果为准。如果数量为 0，先停止。
成功后执行：
ls -lh "$st_work/before"
grep '^validation_scope=' "$st_work/session.conf"
预期至少包含：
core_before.scs
device_catalog.tsv
geometry.tsv
mos_inventory.tsv
以及：
validation_scope=structure_only
