---
name: foran
description: Use FORAN V80R3.0 (SENER ship design suite) for any hull-form, compartment, hydrostatics, or FORAN project work. Trigger whenever the user mentions FORAN, SENER, FBASIC, FGA, FSURF, FDM, FCS, `.db`/`.fsf` ship projects, hull lines, Build Ship, general arrangement, compartments, hydrostatics/stability, DXF lines/GA drawings, or asks to model or calculate a ship hull without the GUI. Also trigger for parametric hull generation (`foran hull`), hydrostatics (`foran hydro`), BREP/STEP solid import, or debugging FORAN startup/license/journal/DB problems — even if the user does not say "FORAN" explicitly.
---

# FORAN V80R3.0 使用技能

本技能把 FORAN 的启动、项目库结构、四个模块的操作流程、日志和 GUI 自动化收在一起。所有路径/许可由用户配置。**先读红线，再按决策树选工具。**

> 本 skill 不包含课程/项目专用的交付包命令，也不包含从帮助/环境导出的命令清单。

## 红线（必须遵守）

1. **不要直接运行 `fbasic.exe` 等 exe**。走官方 `.bat` 链或本技能的 `foran launch`。
2. **不要随意改全局 `LM_LICENSE_FILE`**。优先只对 FORAN 子进程设置，或在 `config.toml` 指定 `license_file`。
3. **不要写原始项目库**。查询用只读脚本；要改先 `foran db copy`，在副本上操作。
4. **不要修改 FORAN 安装目录里的文件**；配置放在外部 `config.toml` 或本技能目录。
5. **启动 GUI、点击、输入前先向用户确认**，除非用户已明确要求“打开/操作 FORAN”。GUI 脚本的 `click/type/keys` 默认拒绝执行，必须显式加 `--yes`。
6. **不要猜 FCS 宏语法**。先录制一段参考操作；命令名以官方帮助/录制结果为准。

## 0. 先自检

```bash
# 第一次在新机器/新项目使用：写 config.toml 并检查环境
foran setup
foran env check
# 若提示 Permission denied（Windows 复制后常见），改用：
# bash foran env check

# 一键自检：环境 + Python/GUI 依赖 + 脚本编译 + 模板 + 可选数据库
foran selftest --db <db>
# 加 --gui 会额外启动并关闭 FDM 与 FSURF（约 30 s）
# 加 --fbasic <db> 会复制该库、启动 FBASIC 选库并关闭（约 30 s）
```

- `status: OK` 才继续。
- `foran selftest` 逐项打印 `[OK]/[WARN]/[FAIL]`；有 `FAIL` 时退出码 1，`--json` 输出机器可读结果。
- 缺许可/缺包装脚本/模块 exe 缺失时，先看 `references/troubleshooting.md`。
- 环境变量覆盖方式见 `references/installation.md` 第 7 节。

## 1. 决策树

| 用户想做什么 | 用什么 |
|---|---|
| 打开 FORAN（FBASIC/FGA/FSURF/FDM） | `foran launch <module>` |
| 看项目库里有什么/查静水力/查肋位 | `foran db ...`（只读） |
| 在副本上做作业/改模型 | `foran db copy` → `foran launch ... --project <副本>` |
| FORAN 打不开/报错 | `foran journal summary` → `references/troubleshooting.md` |
| 怀疑环境/依赖/脚本有问题 | `foran selftest --db <db>`（逐项 OK/WARN/FAIL） |
| 重复性操作想自动化 | `references/macros.md` + `foran macro ...`（录制优先） |
| 想用脚本真正建模/画图 | 本 skill：`fsf`/`fbasic`/`fga`/`draw`/`pipeline` 走 GUI 自动化，`fga spaces/tree` 直接读库 |
| FGA 导出舱室/树 | `foran fga spaces/tree --db <db> --out <tsv>` |
| 把外部闭合实体导入成 FGA 舱室 | `foran fga brep --db <db> --brep <solid> --node CARGO` |
| 参数化生成船体/型线（无 GUI） | `foran hull gen ... --brep`（见第 8 节） |
| 算静水力/与 FBASIC 对比 | `foran hydro calc/compare <db>`（见第 8 节） |
| FGA 出总布置图 DXF | `foran fga draw --db <db> --out <dxf> --copy` |
| 在 FBASIC 里批量算（水密船体/静水力/横截曲线/舱容/干舷/吨位） | `foran fbasic wh/hydro/cross/capacity/freeboard/tonnage`（见第 6 节） |
| 完整稳性：空船重量分布 + 装载工况 | `foran fbasic lsw --tsv zones.tsv` → `foran fbasic lc --lsw LSW-xx`（见第 6 节） |
| 打开/导出 `.fds` 报告（PDF/DOCX/CSV/DXF/SVG/PNG） | `foran fdm open --fds ...` / `foran fdm export --fds ... --out ...`（见第 3 节） |
| 从现成 `.fsf` 出型线图 DXF | `foran draw --fsf <fsf> --out <dxf>` |
| 示例 FSF 线性变换（改主尺度，含删甲板/舱壁） | `foran fsf transform --fsf ... --lpp ... --breadth ...` |
| 出型值表 / 静水力校核（FSURF） | `foran fsf offsets --fsf ... --out ... --hydro <T1,T2> --expect <T:vol:Cb,...>` / `foran offsets parse --lis ...` |
| DWG → DXF（AutoCAD 无界面） | `foran dxf dwg2dxf --in x.dwg --out x.dxf` |
| DXF → DWG（交付用，AutoCAD 无界面） | `foran dxf to-dwg --in x.dxf --out x.dwg` |
| 型值表 + 横剖面面积曲线（CSV/XLSX/SVG/PNG） | `foran offsets export --lis offsets.lis --out-prefix SAMPLE --stations 21` |
| 型线 DXF 加图幅/标题栏 | `foran dxf frame --in lines.dxf --out framed.dxf [--fit --sheet A1] [--template frame.dxf [--template-area auto|x0,y0,x1,y1]]` |
| 一条命令：FSF → 型线 → 套图框 | `foran draw --fsf model.fsf --out lines.dxf --frame-template frame.dxf --frame-out framed.dxf` |
| 批量建横舱壁（X=k） | `foran fsf bulkheads --fsf model.fsf --x 46.85,60.95,91.38` |
| 批量建参数化甲板（主甲板/内底/艏楼） | `foran fsf decks --fsf model.fsf --deck "1:MainDeck:14.8:Main" --deck "9:InnerBottom:2.0:Double-bottom"` |
| 双壳内壳预设（主甲板+内底+双舷内壁+横舱壁） | `foran fsf inner-shell --fsf model.fsf --main-deck-z 14.8 --bottom-z 2.0 --side-y 12.5 --x 46.85,60.95` |
| 带 hopper 折角的双层底内底 | `foran fsf hopper --fsf model.fsf --z 2.0 --flat 11.0 --slope 3,1.5 [--trace 60:0:9.0]`（或 `inner-shell/workflow --hopper 3,1.5 --flat-halfbreadth 11`）；双折角加 `--flat2 11 --slope2 2,0.8`；沿船长折点用 `--hopper-trace 60:0:9`；重跑加 `--replace` |
| Topside tank（Upper-Tanks 甲板，需先有主甲板） | `foran fsf upper-tank --fsf model.fsf --l 8 --h 3.3 --alpha 45 [--replace]`（或 `inner-shell/workflow --upper-tank 8,3.3,45`） |
| 让我“看着屏幕点”/截屏 | `foran gui ...`（先截屏，再控件，再点击） |
| 想知道某个菜单/按钮干什么 | `references/modules/<module>.md` |

## 2. 项目库（最常用）

```bash
S=foran

# 体检：完整性、版本、关键表
$S db check "<db>"

# 复制到工作目录（改写前必做）
$S db copy "<db>" --out-dir ".\_foran_work\projects"

# 静水力 + Cb/Cp 口径
$S db hydro "<db>"

# 找表/字段
$S db tables "<db>" --filter HYD --counts
$S db search "<db>" tank
$S db schema "<db>" DSG_HYD_RESULTS

# 任意只读 SQL
$S db query "<db>" -s "select * from FORAN_VERSION"
$S db query "<db>" -s "select NUM_FR,ABS_FR,DSC_FR from DSG_FRAME_LIST order by NUM_FR limit 10"
```

- 默认 `--format table`；要程序处理加 `--format json`。
- 默认最多 200 行，`--limit -1` 不限。
- 表结构、关键字段、Cb 口径和坑：(未随本 skill 提供)。
- **只读是硬保证**：连接串 `mode=ro` + `PRAGMA query_only=ON`；`query` 拒绝非 SELECT。

## 3. 启动模块

```bash
# 先看计划，不启动
$S launch fdm --dry-run

# FDM / FSURF 不需要库
$S launch fdm
$S launch fsurf --workdir ".\_foran_work\fsurf"

# FDM 打开一份 .fds 报告（自动 File > Open，校验窗口标题）
$S fdm open --fds "_foran_work/fdm/sample.fds"

# FDM 导出报告：格式由扩展名决定（docx/pdf/csv/dxf/odt/png/svg）
$S fdm export --fds "_foran_work/fdm/sample.fds" --out "_foran_work/fdm/export/report.pdf"
$S fdm export --fds report.fds --out page.png --pages current   # 或 --pages all


# FBASIC / FGA：复制库再启动（推荐）
$S launch fbasic \
  --project "C:/FORAN\projects\sample.db" \
  --copy-project ".\_foran_work\projects"

# 不复制、直接开原库（只建议只读查看，且用户明确同意）
$S launch fga --project "C:/FORAN\projects\sample.db"
```

- 启动器自动设置 `LM_LICENSE_FILE` / `FORAN_CONF`，优先用包装 bat。
- 默认**不等待** GUI 退出；需要阻塞用 `--wait`。
- `fbasic`/`fga` 没给 `--project` 时会弹 `Database settings`，由用户在界面里选；也可以用 `foran gui fill-db --project <db> --yes` 自动填。
- FGA/FBASIC 在 `Database settings` 选库之后才加载项目；`foran fga/fbasic ... --db <db>` 会自动选库（见第 7 节）。
- 不要假设 `-fnam` 开关可用；`--pass-fnam` 只是实验选项。
- 详细路径/许可/回滚：`references/installation.md`。

## 4. 排障

```bash
$S journal list
$S journal summary --latest
$S journal errors --latest
$S journal tail --latest -n 30
```

`journal` 会同时扫描 `C:/FORAN\logs` 和 `%USERPROFILE%\.foran\journal`；**GUI 里的报错通常只写后者**。遇到任何意外弹窗，先跑 `foran journal summary --latest`（或 `errors --latest`）看 `DLGMESSAGE`，再截图/点按钮。

先看日志里的 `HEADER`（模块/版本）和 `DLGMESSAGE`（真实报错）。常见对照表在 `references/troubleshooting.md`：

- `WinSock: Connection refused` → 许可被 MSC 变量劫持。
- `Invalid database file.` → 选错/损坏的 `.db`。
- `Database ... is locked` → 库只读/被占用，先复制。
- `Journal folder does NOT exist` → `FORAN_CONF` 没生效。

## 5. 宏（FCS，Tcl）

```bash
$S macro where
$S macro list --workdir "."
$S macro new load_surface --workdir "." --note "加载型线"
$S macro record-help
```

- 可靠流程：GUI 里 `Tools > Macros > Macros recorder` 录一遍 → `Macros editor` 编辑 → `Refresh menu` → 运行。
- 没有文档化的无头运行方式，**不要双击 `.mac`**。
- 文件是 ASCII/Tcl，默认在工作目录；详细说明见 `references/macros.md`。

## 6. GUI 自动化（截屏/控件/点击）

> 必须用技能 venv 运行（pywinauto/pyautogui 装在 `.\.venv`）。`scripts/foran` 会自动优先选它。

```bash
$S gui windows --filter foran
$S gui screenshot --window "FORAN Document Manager"
$S gui controls --window "Database settings" --backend uia --dump ".\_foran_work\controls.txt"

# 点击/输入必须 --yes；先 --dry-run 看计划
$S gui click --window "Database settings" --name "Open DB file" --dry-run
$S gui click --window "Database settings" --name "Open DB file" --yes

$S gui type --window "Database settings" --text "C:/FORAN/projects/sample.db" --yes --enter
$S gui keys --window "FORAN Document Manager" --keys "ctrl+o" --yes

# 自动填 FGA/FBASIC 的 Database settings（走 ... 浏览框，避开 Qt 输入框清空问题）
$S gui fill-db --project "C:/FORAN/projects/sample.db" --fnam sample --yes
```

规则：

1. 先 `windows` 确认标题，再 `screenshot` 留底。
2. 控件找不到时换 `--backend win32`；仍不行用 `click --pos x,y`（屏幕坐标）。
3. 每次点击/输入前后各截一张图，向用户展示结果。
4. 危险操作（删除、覆盖、确认更新库）必须先问用户。
5. **实测**：FDM 主窗口的 MenuBar/ToolBar 暴露 UIA（`Open`、`Export active` 等），但 File 下拉的 QPopup 菜单项不暴露 UIA，点菜单需坐标；`Open` 文件对话框是 Win32 `#32770`。`foran fdm open --fds` 与 `foran fdm export` 均已验证。Export 对话框是 Qt 自绘控件（UIA 只有 Custom），格式下拉的列表项点击会穿透 → 用“点下拉 → Esc → Down×N”选格式（N=列表序号）。PNG 需要页面已渲染，页视图空白时 FDM 会弹 `Image file generation failed`（此镜像上 sample.fds 即如此，改用 pdf/dxf/svg）。
6. Qt/OpenGL 窗口可能截图全黑或控件树为空；见 `references/troubleshooting.md` 第 5 节。

## 7. GUI 自动化与读库

本 skill 用两种方式驱动 FORAN，都只依赖公开的界面和项目库：

- **GUI 自动化**（需要配置 `wrapper_dir`）：`foran fsf build/transform/decks/bulkheads/inner-shell/hopper/upper-tank/workflow/offsets`、`foran fbasic wh/hydro/cross/capacity/freeboard/tonnage/lsw/lc`、`foran fga draw/brep/import-hull`、`foran draw`（含 `--build-ship`）。
- **读数据库**：`foran fga spaces/tree/export` 直接查已保存的项目库（`DSG_SPC_TREE`/`DSG_SPC_PROPS`/`DSG_GSF_TREE`/`DSG_COMPT_TREE`），不启动 FGA。
- `foran pipeline` 调用上述命令；要求项目库里有 `CARGO` 工作区节点（样例库只有 `Ship`/`HULL`，会停在 Space selection）。

> GUI 自动化要求 `wrapper_dir` 指向可用的模块包装 bat；官方 bat 在本机默认
> `FORANDISK=C:\FORAN`，会启动失败。详见 `references/installation.md`。

## 8. 参数化船体与静水力（无 GUI）

这两个命令不启动 FORAN，直接用 Python 完成“建模 + 计算”，适合批量方案、快速估算和交叉验证。

### 8.1 参数化船体

```bash
S=foran
$S hull gen --lpp 172 --breadth 28.8 --draught 9.83 --depth 14.6 \
  --cb 0.83 --stations 21 --out _foran_work/hull/demo --brep
```

- 船体由站截面生成：`y(x,z)=A·(B/2)·f(u)·g(v)`，`f` 是纵向丰满度，`g` 是垂向截面形状。
- 自动用二分法调 `g` 的指数，使 **Cb 命中 `--cb`**（达不到时自动放大 `A` 并报告）。
- 输出：`sections.json`、`lines.svg`（横剖/纵剖/水线）、`hydro.json`、`report.md`；`--brep`/`--step` 再用 gmsh 生成闭合实体。
- 实测：172/28.8/9.83/14.6、Cb=0.83 → p=0.0185、volume=40,415.927 m³、disp=41,426.325 t、LCB=84.129、KB=5.068；BREP 全船体积 60,752.809 m³（与截面积分到 D 完全一致）。
- 生成的 BREP 可以直接 `foran fga brep --brep hull.brep` 导入 FGA（实测 volume=60,752.809、bbox x0..172/y±14.4/z0..14.6）。

### 8.2 静水力

```bash
$S hydro calc "<sample.db>"                      # 设计吃水
$S hydro calc "<sample.db>" --drafts 1,4,6,8,9.83
$S hydro calc "<sample.db>" --json > hydro.json
$S hydro compare "<sample.db>"                   # 与 FBASIC 的 DSG_HYD_RESULTS 对比
```

- 直接读 `DSG_SOLID_HULL_SECTIONS`：每行一个站，`DATA` 是 12 字节头 + 每点 5 个 big-endian float32（前两个是 Y/Z）。
- 输出：Volume、Displacement、Cb、Cp、Cm、Cwp、LCB、LCF、KB、BM_T、KM_T、TPC、MCT、Awp、Wetted。
- 实测 sample、T=9.83：Volume 40,373.57 vs FBASIC 40,383.13（-0.024%）；Cb 0.82913 vs 0.82933；LCB 90.417 vs 90.403；KB 5.1474 vs 5.1469；KM_T 12.3388 vs 12.3361；TPC 47.032 vs 47.083；MCT 594.05 vs 596.27。**除 Wetted 约高 2.4% 外，其余都在 0.1% 内**。
- 只支持 **正浮（even keel）**；带纵倾/横倾的水线暂未实现。

> 这是目前“无人工”的建模+计算闭环：`hull gen` 造型 → `hydro calc` 算性能；需要进 FORAN 时，把 `hull.brep` 用 `fga brep` 导入。
> FSURF 的 `File > Import > Import/Merge` 支持 IGES/STEP/BREP，生成的船体可以导入，但实体导入会变成 **862 个 patch**；Manager 里把 `Surface Entities` 组拖到 `External Hull` 会报 `Can't add this kind of object.`。
> 用 `nz=4` 粗截面 + `makeSolid=False` 可以生成 **11 个 patch** 的壳；Build Ship 能填字段、Surface Validator 也能过，但 `Finish` 报 `Ship has not correctly assembled`——patch 还在 Work Space，没分配到 External Hull。Manager 对 11 个 patch 仍只显示类别行，展开不出具体 patch。下一步要找到 Manager 的 patch 列表/批量分配方式。

## 9. 输出约定

- 所有临时产物放当前项目目录的 `_foran_work/`：
  - `_foran_work/projects/` 项目库副本
  - `_foran_work/backups/` 启动前备份
  - `_foran_work/screenshots/` 截图
  - `_foran_work/macros/` 宏草稿
- 不要写到 `C:\Program Files\FORAN`、`C:/FORAN`（除非用户明确要求改配置）。
- 默认工作目录是当前目录。

## 10. 参考文档

| 文件 | 内容 |
|---|---|
| `references/installation.md` | 路径、许可、conf、启动、回滚、换机器 |
| `references/troubleshooting.md` | 症状 → 原因 → 处理 |
| `references/journal-format.md` | 日志格式与解读 |
| `references/macros.md` | FCS/Tcl 宏录制与文件管理 |
| `references/hull-hydro.md` | 参数化船体、Cb 校准、BREP、静水力公式与 FBASIC 对比 |
| `references/modules/fbasic.md` | 性能计算：静水力/稳性/干舷/吨位/破舱 |
| `references/modules/fbasic-stability.md` | Stability Tree、确定法/概率法破舱、Reg.7/8/9 |
| `references/modules/fga.md` | 分舱与总布置（含选库/树/GA 出图） |
| `references/modules/fsurf.md` | 型线/曲面建模、船型变换、型线图 |
| `references/modules/fdm.md` | Document Manager |
| `references/portability.md` | 换机器/换分辨率的验证清单（哪些仍是坐标依赖、怎么重新量） |
| `references/gui-automation.md` | UIA/坐标/DPI 分层、校准流程、点击安全规则 |
| `scripts/foran_ui.py` | 共享 UIA 助手（菜单名点击、QPopup 枚举、标签旁的输入框、关闭并应答对话框），fbasic/fga/fsf 共用 |

## 11. 依赖与安装

- `env/launch/db/journal/macro` 只用标准库。
- `hydro`、`hull` 也只用标准库（`hull --brep/--step` 需要 `gmsh`）。
- `gui`、`draw`、`fga` 需要 `pywinauto`、`pyautogui`、`Pillow`、`pyperclip`：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r .claude/skills/foran/scripts/requirements.txt
```

- `hull gen --brep/--step` 和 `fga brep --box` 需要 `gmsh`（已列入 requirements）；不用实体导出时不装也能跑。
- 本沙盒已建好 `.\.venv`。
- 换机器先跑 `foran setup`（写 `config.toml` 并检查），或改 `FORAN_SKILL_*` 环境变量后再 `foran env check`。

## 12. 已知限制 / 待核实

- 宏文件的实际扩展名（本技能默认 `.mac`）需以录制器输出为准。
- FCS 宏没有无头运行入口；只能从 GUI 菜单运行。
- `foran draw` 已能打开 `.fsf` 并生成型线图 DXF。
- **Build Ship 的 Surface Validator 已自动走完**：`--build-ship` 会逐页 `Analyze` → 点状态列右侧 `Open` → `Checked`；Duplicated/Lines 用 `Analyze all surfaces`；Finish 后会有校验日志 warning（正常），并写出新 `.fsf`。
- **Build Ship 字段映射已打通**（2026-10-26）：Build Ship 对话框的 UIA Edit 可按标签定位；`foran draw --build-ship --build-lpp/--build-breadth/--build-draught/--build-depth`（以及 `--build-field "Label=Value"`）可直接改主尺度并写入新 `.fsf`。Qt Edit 不支持 `set_value`，实现用 click + ctrl+A + 剪贴板 + Tab；
- **FSURF 壳导入 → Build Ship → 型线图全自动已打通**（2026-10-26）：`foran fsf build` 导入低 patch BREP 壳、Manager 逐个 patch 拖到 `External Hull`、Build Ship/Validator、定义肋位、保存带肋位的 FSF、出 Lines Drawing DXF。拖放点必须落在行文字上（整行宽矩形中心是空白），`File > Save` 需要填 `Save File` 对话框且文件名必须走剪贴板（中文输入法会改字），详见上文第 7 节。
- **六限界最终结论（2026-10-27）**：开放壳、闭合 IGES（77 patch）、FSURF 13 面闭合壳（11 侧面 + 艏艉封盖）都试过；FSURF 表面在 FGA 里**无 Free edges**，但有 `Overlapped edges`，`Fix shape`（0.0005/0.01/0.1）修不掉；六格填对（`x50–80 / y±4 / z2–8`）后 `Build Space` 仍报 `Recalculation of subspace(s) SUBSPC-0001 failed`。结论：六限界被 FORAN 的 patch 重叠/重算逻辑卡住，不是缺端面。继续用参数化 subspace 或 `foran fga brep` 导入实体。
- **六限界表格坐标**：数据行在 **y≈793–822**（不是 773，773 是表头边界）；Aft 单元格 x≈589–688。按 773 点会导致 Aft 一直为 0。UIA 的 `DataItem` 可直接读到 `x/y/z ... m`，优先用它校验。
- `foran draw --scale` 现在能写入 Lines Drawing 的 `Scale` 输入框（Qt spin box 需用键盘输入，剪贴板无效）。默认 100；`--scale 300` 生成的 DXF 与参考交付图逐字节一致。
- FGA/FBASIC 是在 `Database settings` 选库**之后**才加载项目；`foran fga/fbasic ... --db` 会自动处理。
- `foran fga draw` 的菜单/树点击坐标按 1920×1080 最大化布局测量；换分辨率或窗口布局后需要重新校准。它按“新建图纸是 Ship 的第一个/唯一子节点”选中，已有多个 GA 图纸时需人工确认。
- FGA 新建舱室：编辑器流程已摸清（需先锁定项目/树，再把节点 `Set active` → `New space`）。**参数化子舱室**已实测可建模/保存/导出（圆柱体积 94.2478 m³，COG/bbox 正确）；**六限界**见上一条最终结论（暂缓）。详见 `references/modules/fga.md` 8.1。
- Qt 控件对 UIA 的暴露程度因模块/版本而异；必要时退回截图 + 坐标。
- `-fnam` 传库路径未验证；默认让 GUI 弹框选库。
- 项目库的表很多且可能为空；不要凭表名猜数据。
