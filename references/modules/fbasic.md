# FBASIC — 性能计算（FORAN Basic Design）

FBASIC 基于项目库里的船体/舱室/重量数据做静水力、稳性、干舷、吨位、破舱、舱容、测深、下水等计算。它和 FGA 共享同一个 `.db`。

> 来源：实际操作经验整理。软件 V80R3.0；菜单名以实际界面为准。

## 目录

1. [启动与前置条件](#1-启动与前置条件)
2. [系统配置](#2-系统配置edition--preferences)
3. [辅助工具](#3-辅助工具)
4. [Entities Tree](#4-entities-tree)
5. [Calculation Tree](#5-calculation-tree)
6. [Stability Tree](#6-stability-tree完整稳性)
7. [概率破舱](#7-概率破舱probabilistic-damage-stability)
8. [结果与报告](#8-结果与报告)
9. [常见坑](#9-常见坑)

## 1. 启动与前置条件

```bash
S=foran
$S launch fbasic --project "<db>" --copy-project ".\_foran_work\projects"
```

计算前必须先在 `Entities tree` 定义：

- `Water tight hull`（水密船体）——所有计算的基础；
- `Lightship weight distribution`（空船重量）；
- 按需：附体、进水点、限界线、波浪、受风面积、测深线、模块化货物等。

节点操作前先右键 `Lock`（或 `File > Lock All`），否则命令灰掉。

## 2. 系统配置（Edition > Preferences）

| 项 | 作用 |
|---|---|
| `Entities naming pattern` | 辅助对象自动命名（前缀+序号） |
| `Calculation naming pattern` | 计算结果自动命名 |
| `References` | 长度基准：`Aft perpendicular`（默认）/`Fore Perpendicular`/`Midship` |
| `Tolerances` | 体积/面积/长度/角度公差；越小越准、越慢 |
| `Units` | 长度/角度/重量单位 |
| `Hydrostatic calculation` | 水密度（默认 1.025）、外板厚、龙骨厚、吃水表达、舵/桨引用 |
| `Intact` | 完整稳性：`Standard`/`Ship on wave`、重心修正、GM 基准、自由液面修正、横倾角列表 |
| `Longitudinal Strength` | 总纵强度校核设置 |
| `Flooding Calculation` | 破舱：`Lost of Buoyancy`（默认）/`Added weight`、自由液面、中间进水阶段、甲板积水（Stockholm） |
| `Max KG Calculation` | `KG tolerance`、`Bisection`/`Incremental`、是否用 intact KM 限制 |
| `Print` | 报告内容（稳性曲线、总纵强度曲线、破损草图等） |

## 3. 辅助工具

### 3.1 Point definition

- 坐标写法：绝对值 `21050`；肋位+偏移 `fr25 + 200`；相对垂线 `AP+5500`；参考面+偏移 `'bhd70' -250`。
- 勾 `scene clicked change coordinates` 可在 3D 视图拾取。
- `Calculate` 求解，`solution points` 列表里勾选。

### 3.2 Project Main data

命令：`Tools > project`。主尺度（L、B、D 等）在这里维护；FSURF `Build Ship` 的数据也会进来。

## 4. Entities Tree

### 4.1 水密船体（Watertight Hull）

1. 右键 `Water tight hull Definition > New Hull`，输入 `Name`。
2. `Method` 顶部限界面：
   - `Height`：直接输入高度；
   - `Decks`：选甲板作顶界，可多层并设作用范围（如 `fr76`）。
3. `Build WH` 生成。
4. 注意：顶界从后往前定义，且要与型线有交点。
5. `Hull Sections`：自动分割；`Add`/`Remove` 自定义剖面；`Reset All` 重自动分割（自定义丢失）。

**从闭合 BREP/space 建 WH（2026-10-27 实测，推荐用于生成船体）**：

1. 先把闭合 BREP 用 `foran fga brep` 导入成 FGA space（`SPC-xxxx`，`DSG_SOLID_DIR` 带 OCC_SOLID）。
2. `Entities > Watertight hull definitions > SOLID-01 > Edit`。
3. `Method` 下拉选 `Spaces`；点 `Spaces` 行的绿色 `+` → `Space selection` 勾选该 space → `OK`。
4. `Build WH` → 3D 显示船体；`Sections` 变可用 → 点击 → `Do you want to calculate the default sections?` → `Yes`。
5. `Ok` → `File > Save`。实测 `DSG_SOLID_SECTS` 74 行、`DSG_SOLID_HULL_SECTIONS` 69 段。
6. 之后 `Parallel hydrostatics calculations` 才能计算；否则报 `Watertigh hull sections are not calculated`。

**自动化（2026-10-27）**：

```bash
S=foran
$S fbasic wh --db <db副本> --space SPC-0003 --build
```

完成第 2–5 步（Edit → Method=Spaces → Space selection → Build WH → Sections → Ok → File Save）并校验 `DSG_SOLID_DIR` / `DSG_SOLID_HULL_SECTIONS`。实测副本 `saved=True`、`hull_sections=69`。只打开 Edit 面板用 `--keep-open`（不加 `--space`）。

> 开放壳（`makeSolid=False`）不要直接 `Build WH`：会删掉原主船体实体且不生成新实体。

### 4.2 附体（Appendages）

- 螺旋桨：`New Propellers`；`Type` = `Diameter` 或 `Volume`；定位 `X-Position`、`Abscissa of minimum height`、`Minimum height`。
- 舵：`New Rudder`；`Type` = `By Dimensions` 或 `Volume`。
- 其他：`New Appendage`，仅用于浮态，不影响排水量。

### 4.3 水尺（Draft marks）

`New Draft marks`：`Abscissa`（X）、`Height over BL`（最低点距基线）。

### 4.4 进水点（Openings and connections）

- `New opening`；`Integrity`：
  - `REF` 参考点，不影响计算；
  - `DOWN` 风雨密，不限制稳性；
  - `FLUSH` 未保护，影响浮态/稳性。
- `Geometry` 定义坐标；`Space A` 关联舱室。
- 勾 `internal opening` 表示内部进水点：设 `Space B`、`Flow direction`、`Section area`、`Friction factor`。
- 右键 `Import openings from FILE` 批量导入。

### 4.5 限界线（Margin lines）

`New line`；`Method` = `By decks list`（甲板+偏移）或 `point list`（点列）。

### 4.6 空船重量（Lightship weight distribution）

1. 右键 `Lightship weight distribution` → `New distribution`，填 `Name`；表格可从 Excel 复制（TSV），在第一个数据格 `Ctrl+V` 粘贴。列：`Group / Name / Description / Ref. number / Weight / X min / X max / XCoG / YCoG / ZCoG`。`Group` 留空会自动填 `Structure`。
2. **`X min/X max` 必须是各分区真实的纵向范围**：按 XCG 排序后用相邻 XCG 的中点作边界，首区从船体 Xmin、末区到 Xmax。所有行都填同一范围（如 0–172）会让网格无效，LS 报 `LSW distribution not calculated`。
3. 粘贴后 `Total weight` 显示 0，直接 `Ok` 会把根节点写成 0。**再右键该分布 → `Edit distribution`**（标题 `... edition`），`Total weight` 会自动算成 ΣWeight / XCG / ZCG，再 `Ok`，根节点才为 8650。
4. **计算分布**（关键）：右键分布 → `Edit complex distribution` → `OK` → 弹 `Remainder weight distribution warning`（偏差 > 0.0001·L）→ `Ok` → `File > Save`。成功后 `DSG_LSW_DIST_RESULTS`（逐帧）、`DSG_LSW_DIST_TOTAL_RESULTS`、`DSG_LSW_CONT_WEIGHT` 均有行。
5. `Continuous weight ...` → `Continuous longitudinal weight`：`Type of ship` / `ZCG` / `Upper deck` / `Calculation type`（Automatic 会按船型估连续重量）。
6. `Remainder` 显示负值（如 -8650）不影响计算与 LC；不要用 `Reset remainder` 强行归零。
7. 分布写库后，**重启 FBASIC** 再进 LC，`Update`/`Calculate` 才不会报 `LSW distribution not calculated`（同会话内是旧缓存）。
8. 右键 `Report` 不可用于计算分布：报表模块会报 `Invalid definition of grid cell widths`，关闭错误框还可能使 fbasic.exe 退出。

**CLI（2026-10-27 实测通过）**：

```bash
# TSV 列：Group / Name / Description / Ref / Weight / Xmin / Xmax / XCoG / YCoG / ZCoG
S=foran
$S fbasic lsw --db <db副本> --tsv zones.tsv               # 自动命名 LSW-xx
$S fbasic lsw --db <db副本> --tsv zones.tsv --name LSW-04
```

`lsw` 内部按上述 1–4 步执行，并额外处理：粘贴后先点 Name 字段提交表格编辑，再点 `Ok`（有时弹 Warning/Information，脚本会自动关闭并重试一次）；新节点名用**树节点差集**识别（保存前 DB 里还没有新记录）；`_dismiss_modal` 负责关掉 Remainder 警告。校验项：根节点 `WEIGHT` = TSV 合计、`DSG_LSW_DIST_RESULTS > 0`、`DSG_LSW_DIST_TOTAL_RESULTS > 0`，任一不满足即返回 1。

实测（`_foran_work/fbasic/proj/cli_lsw_test.db`，17 区 TSV）：`LSW-02 root_weight=8650 dist_rows=244 total_rows=1`，总表 8650 t / XCG 79.302。

`--name` 可用：Name 框默认预填下一个自动名（如 `LSW-02`），脚本会先 `Ctrl+A` 全选再粘贴，否则会拼成 `LSLSW-09W-02`；自定义名建议仍用 `LSW-<数字>`，自动识别依赖该格式（显式传入其他名字时按名字查找，也能工作）。实测 `--name LSW-09` → `LSW-09 root_weight=8650 dist_rows=244`。

### 4.7 波浪（Wave Profile）

`New wave`；`Type` = `sinusoidal` / `trochoidal`；`Position` = `Hogging`（波谷在尾）/`Sagging`（波峰在尾）/`User Defined`。

### 4.8 受风面积（Wind profile）

1. `New profile`；`Method` = `Interactive`（3D 取点，可投影 `Point at Y=0`）或 `Imported`（`.dat`/`.pol`）。
2. 右键曲线 `Report`：输入 `Wind pressure`、`Trim value`、`Minimum/Maximum middle draught`、`Increment`，生成特性表。

### 4.9 测深线（Sounding lines）

`New line`：`Sounded space` 选舱室；控制点 `(X,Y,Z)`；`Increment` 计算点间距；`Discount` 结构扣除率；`Display` 预览。

### 4.10 模块化货物（Modular cargo）

1. `Container types > New`：长宽高、最大/默认重量、重心。
2. `Groups > New`：选 `Container type`；`Reference point`；`Elements`（Nx/Ny/Nz）；`Bounding Space` 选舱室；`Update` 预览。
3. `Arrange > New arrangement`：选 `Groups`。

### 4.11 暴露表面（Exposed surfaces）

`New`：`Area`（投影面积）、`Height over BL`、`Shape coefficient`。

### 4.12 图面布局（Layouts）

`New`：定义纵剖/横剖/水平剖位置；右键 `Set active` 设为默认。

### 4.13 弯矩/剪力限界线

`New Curve`：输入 X 及对应的最大/最小剪力、弯矩。

## 5. Calculation Tree

### 5.1 静水力（Parallel hydrostatics calculation）

1. 右键 `Parallel hydrostatics calculations > New calculation`；输入 `Water density`。
2. `Options`：
   - `Waterline system`：按吃水算；设 `Initial Draught`、`Trimming`、`Heel`；可用 `Draught net`（吃水组）或 `Additional draughts`。
   - `Displacements Net`：按排水量算。
3. `DEFORMED WATERLINES`：可选抛物线/多段线水线面。
4. `CALCULATE`。
5. 结果：右侧表格 + 下方曲线。
6. 输出：右键 `Export`（xlsx）或 `Report`（fds）；`Bonjean values report` 输出邦戎曲线数据。

**实测细节（2026-10-27）**：

- 启动时若弹 `Warning: The ship's profile is not defined. Calculations will be much slower`，点 `Ok` 即可，非致命；没有 profile 只是算得慢。
- `Waterline system` 默认没有任何吃水行：点 `Draughts net` 右侧绿色 `+` 新增一行 `Draught`，双击/点击数值格填 `Draught value`（如 `14.6 m`）和 `Increment`（如 `1.0 m`）；再点 `Calculate`。
- 计算时出现 `Please wait`，完成后右侧表格按吃水逐行给出 `Aft/Fore/Middle draft`、`Trim`、`Displacement (t)`、`Moulded volume (m3)`、`X.CB` 等，下方曲线同步。
- 如果 `DSG_SOLID_DIR` 里没有主船体实体（`Build WH` 失败或未建），点 `Calculate` 不会报错，但结果表为空。先确认 Entities 树里有 `SOLID-01` 且 3D 视图能看到船体。

**自动化（2026-10-27）**：

```bash
S=foran
$S fbasic hydro --db <db副本> --calc HYD-CALC-01
```

自动打开已有 `HYD-CALC-*` → `Calculate` → 等 `Please wait` 真正结束（约 1–2 分钟/60 水线）→ `Ok` → `File > Save`，并打印 `DSG_HYD_RESULTS` 中 9.83 m 行。实测副本 58 行：41,432.117 t / 40,421.578 m³ / Cb 0.8301 / KM_T 11.6409。

**全链路一条命令**：

```bash
$S pipeline hull --db <db副本> --copy --brep hull.brep
```

`pipeline` 依次调用 `fga brep`（导入 space）→ `fbasic wh --space SPC-xxxx --build` → `fbasic hydro`，并校验剖面数和静水力行。启动时的 profile 警告会自动点 `Ok`。

### 5.2 静水力图（Parallel hydrostatics drawing）

- 右键 `Parallel hydrostatics drawings > New`。
- 格式 `.d`（FORAN）或 `.dxf`（AutoCAD）。
- 勾选要出的图：`Sectional Areas Curve`、`Hydrostatics Curves`、`Bonjean Curves`、`Deadweight scale`、`Trim diagram`。
- `Calculation` 生成。

### 5.3 稳性横截曲线（Cross curves）

1. 右键 `Cross curves > Calculation`。
2. 设置：
   - `Deck immersion line`：浸水甲板；
   - `Opening immersion`：`None` / `All` / `Node`；
   - `Calculation to both sides`：默认仅左舷；
   - `Free Trim`：先算平衡水线再算浮心，需额外 KG；默认不勾；
   - `Wave`：波浪样式，默认 `None`（静水）；
   - `Use net of`：`Displacements`（排水量）或 `Drafts`（吃水）；
   - `Displacements`、`Heel Angles`、`Trim values`（尾倾为正）。
   - `Name and Description`、`Water density`。
3. `Calculation`。
4. 结果：
   - 选纵倾/横倾后看 `Displacement`、`Draught in amidships`、`LCB/TCB/KB`、`KN`（基线为参照）、`Trim`；
   - 甲板浸水：`Heel angle`、`Displacement`；
   - 进水点：`Heel angle`、`Displacement`、`Opening`；
   - 底部曲线可点曲线名显示/隐藏。

**自动化（2026-10-27）**：

```bash
S=foran
$S fbasic cross --db <db副本> --displacements 20000,30000,40000,50000,60000
```

- 复用已有 `KNS-CALC-*`（有非零排水量就原样保留）或新建；
- 新建时先点 `+` 建满 5 个空白 `Displacement` 行，再逐行找值为 0 的行填入并 `Tab`；
- 等 `Please Wait...`（大写、带省略号，约 169 s）；
- `Ok` → `File > Save`，实测 `DSG_KNS_CALC_RESULT` 357 行。

注意：`DSG_KNS_CALC_RESULT.DISP` 是**型体积 m³**（×1.025 = 吨）；UI 表里 20000 t 行的 `4.915` 是吃水，不是 KN。
5. 输出：右键 `Export`（xlsx）；`Report`（fds）；`Plot`（dxf/pdf 横截曲线图）。

### 5.4 浸水分析（Flooding analysis）

- 右键 `Flooding analysis > New Flooding analysis calculation`。
- `Type`：
  - `Liquid loads`：往舱内打水后的浮态变化；
  - `Flooding effects`：破损后 GM 变化趋势。
- `Initial situation`：`Displacement`、`Trim`、`ZCOG`、`Corrected ZCOG`。
- `Space`：勾舱室并设渗透率（默认取舱室定义值）。
- 结果：
  - `Liquid loads diagram`：每舱 `WEIGHT`、`HEEL`、`DRAUGHT INC.AFT`、`DRAUGHT INC.FORE`；
  - `Flooding effects diagram`：每舱总进水量 `WEIGHT`、`MOMENT`、25/50/75/100% 进水率下 GM 变化（`+` 变大、`-` 变小、`=` 1% 内）。
- 报告：报告按钮 → 选路径/格式/文件名。

### 5.5 可浸长度（Floodable Length）

- 右键 `Floodable lengths > New Floodable lengths tables`。
- `Initial flotation`：`Aft draught`、`Fore draught`（默认设计吃水）。
- `Margin line`：选已定义限界线。
- `Zones of the ship`：输入尾/首端限界面，分三区。
- `Permeabilities`：`Aft zone` / `Middle zone` / `Fore zone`。
- `Watertight bulkhead`：逐个添加水密舱壁位置。
- `Sea water specific weight`、`Factor of subdivision`。
- `Calculation`；结果含每个位置的可浸长度、许可舱长。
- `Report`（Excel）、`Plot`（dxf/pdf）。

### 5.6 倾斜试验（Inclining test）

用途：求空船重量、重心高、重心纵向位置。

- 右键 `Inclining test > New Inclining test Calculation`。
- 环境数据：地点、人员、海况、风向/风速、气温/水温、水密度。
- `Calculation option`：`2008 IS Code` / `Given GM` / `General readings`。
- `Ship condition`：量艏/中/尾水尺，试验前后对比。
- `Number of weight groups`（默认 4）、`Number of positions`（默认 9）。
- `Positions`：`UPRIGHT` / `PORT` / `STARBOARD` / `NO MOTION`。
- 选项卡：`Experiment readings`、`Additional weights`、`Deduct weights`、`Weights spaces`。
- `Calculate` → `Report`。

### 5.7 下水计算（Launching）

三种：船台静态、船台动态、船坞。

**静态船台**：`Length of grounding ways (XGRND)`、`Slope (AGRND)`、`Camber`、`Length/Width/Height of sliding ways`、`Number of sliding ways`、`Angle between faces`、`Length of fore poppets`、`Initial loading condition`、`XMSLID`、`XFSLID`、`Level of tide (TDLEVEL)`、`Number of calculation steps`。

**动态选项**：`Starting to stop the ship`、摩擦系数算法、`Method to stop the ship`（`None`/`Chain Drags`）、`Starting to stop the ship in slipway`、锚链重量/单位重量/摩擦系数。

**尾部横向挡板**：`halfbreadth at minimum/maximum height`、`minimum/maximum height referenced to b/l`、`Normal area coefficient`、`Situation abscissa ref. to aft perp`。

按钮：`Calculate`、`Report`（FDS）、`Export`（Excel）、`Drawing`（dxf/.d）、`Options`。

**下滑力计算**：`Environment temperature`、`Abscissa of aft/fore stock`、`Launching calculation`、支反力/受力面积列表。

**船坞下水**：墩木上表面与水平面夹角、尾/首墩木坐标、水线数量/额外水线、分布曲线等分数、`Zone`（部分建造状态：船尾/船首坐标、增加/减少排水量的舱室）。

### 5.8 舱容（Capacities）

- 右键 `Capacities > New Capacity Table`。
- `Density`（舱内液体密度）、`Waterline system`（`Number of levels`、`Spacing`）、`Spaces`。
- `Calculate`；`Report`（fds）、`Export`（Excel）。

**自动化（2026-10-27）**：

```bash
S=foran
$S fbasic capacity --db <db副本> --spaces SPC-0002,SPC-0003 --levels 15 --spacing 1.0
```

- `Spacing` 必须 0–10 m（0 报错）；
- `Spaces` 的 `+` 打开 `Spaces selection`：**最大化后右下角才有 OK**，点 `Expand` 展开 CARGO，勾选 SPC 后 OK；
- `Calculate` 的 `Please wait` 到 100% 后不会自动关，自动化会聚焦对话框、扫描绿色进度条，≥90% 时点 `Close`；
- 实测 `DSG_CT_DATA` 1 行、`DSG_CT_SPACES` 2 行。

### 5.9 测深（Sounding）

- 右键 `Sounding > New Sounding Table`。
- `Sounding line` 选已定义测深线；`Heeling net`（横倾角）、`Trim net`（纵倾，尾倾正）；`Table of corrections`（遥控测深点与测深线不一致时修正）。
- `Calculate`；结果列：`X/Y/Z`、`S.L`（测深线长度）、`U.L`（ullage）、`Net Volume`、`Empty Volume`、`LCG/TCG/VCG`、`Flotation Area`、`Inertia transversal`。
- `Report`（fds）、`Export`（Excel）。

### 5.10 干舷（Freeboard）

依据 `International Agreement on Load Lines 1966`（MSC.77 修订）。

- 最小干舷：`Fmin = f0+f1+f2+f3+f4+f5+f6`（基本、船长<100m 修正、Cb 修正、型深修正、上建/围壁修正、舷弧修正、甲板线修正）。
- 还要校核最低船首高度。
- 右键 `Freeboard > New Freeboard Calculation`：
  - `Type of ship`：`A`/`B`/`B60`/`B100`；`Timber carrier ship`；
  - `Freeboard deck`、`Castle/Bridge/Poop deck`（可选 `User define`）；
  - `Superstructure height`（`System Value`/`User define`）；
  - `Depth correction`（`Always` 进行型深修正）；
  - `Freeboard deck thickness at side`；
  - `Effective length`（艏楼/桥楼/尾楼，`System Value`/`User define`）；
  - `Freeboard length`（`System Value`/`User define`）；
  - `Deck line correction`。
- `Calculate` → `Report`（.fds，用 FDM 打开）。

**自动化（2026-10-27）**：

```bash
S=foran
$S fbasic freeboard --db <db副本> [--calc FB-0001]
```

- 自动打开已有 `FB-*`（或新建），`Calculate` → `Ok` → `File > Save`；
- 校验 `DSG_FREEBOARD_DATA` / `DSG_FREEBOARD_RESULTS` 各 1 行。实测 `FB-0001`：Summer 3.787 m 等六工况。

### 5.11 吨位（Tonnage）

依据 `International Convention on Tonnage Measurement of Ships 1969`。

- 右键 `Tonnage > New Tonnage Calculation`。
- `Moulded Depth`、`Moulded Draught`；
- `Passengers (Cabins < 8 berths)`、`Passengers (Others)`；
- `Included spaces`（默认水密船体总体积，可追加甲板室等）、`Excluded spaces`；
- `Included volumes` / `Excluded volumes`（手输追加/排除体积）；
- `Cargo spaces`（净吨用）、`Cargo volumes`。
- `Calculate` → `Report`（.fds）。

**自动化（2026-10-27）**：

```bash
$S fbasic tonnage --db <db副本> --spaces SPC-0002,SPC-0003 [--calc TONN-0001]
```

- `Included spaces` 行绿色 `+` → `Spaces selection`（最大化 + `Expand` + 勾选 + `OK`）；
- `Calculate` → `Ok` → `File > Save`；打印 `TONN-*` 节点。实测 `TONN-0001`，GT 37,156.60 / NT 11,146.98（UI）。

> 这两个命令导航 `Calculations > Naval Architecture > Compartmentation` 时，会先用 `dsgnewndtree` 确保树视图，再用 OpenCV 模板 `templates/fbasic_calc_tab.png` 定位自绘的 `Calculations` 标签（`foran vision`，需要 `opencv-python-headless`）；找不到模板时退回 `(25,320)`。

### 5.12 惯性矩与倾覆力臂（Heeling & Inertial moment）

- 右键 `Heeling & Inertial Moments calculation > New`。
- `Percentage of filling`：`Default`（20/40/60/80/90/95/98%）或 `Incremental`（自定义步长到 100%）。
- `Heeling net`（左倾为正）、`Trim net`（尾倾为正）、`Spaces`。
- `Calculate`；结果：选纵倾、显示惯性矩/倾覆力臂，点列看曲线。
- `Report`（xlsx）。

### 5.13 MARPOL 溢油（Accidental outflow，Annex I 12A/23）

- 右键 `Accidental outflow > New Accidental outflow Calculation`。
- `Basic data`：
  - `Regulation`：`12A`（燃油）/`23`（货油）；
  - `Calculation Side`：`Port`/`Starboard`；
  - `Ship type`（仅 23）：`Oil tanker`/`Combination Carrier`；
  - `Ship data`：`Ds`、`ds`、`Bs`、`dB`、`Bb`、`dP`、`L`、`DW`（可 `Calculate` 自动算；**必须先完成干舷计算**）；
  - `Cargo types`：通常燃油+柴油。
- `Cargo tanks`：`Add tanks` 选舱室，参数自动算，可双击改；`Remove selected`/`Recalculate selected`/`Regenerate table`。
- `Side damage`：舷侧破损概率因子、泄油量；`Os` 可编辑；`Recalculate selected`。
- `Bottom Damage`：`Ob`、`CDB`；12A 低于规范值会警告（OK 继续 / Cancel 回去改）。
- `Nominal density`。
- `Report`：`Load Script` 选 `Mpl12A_doc.fpl` / `Mpl23_doc.fpl`，可编辑模板；`Run` 计算，`Done` 关闭；错误显示在输出区。

### 5.14 阻力/功率预估（Power predict）

- 右键 `Power prediction > New`。
- `Speed range`：`Lower`/`Upper`/`Increment`（kn），`Additional` 额外速度。
- `Draft`：首/尾吃水。
- `General Data`：主尺度自动提取；可勾 `Data defined by` 手输。
- `Calculation method`（阻力估算方法）、`Sections type`（横剖面类型）。
- `Bow bulbous`：第 20 站球鼻面积、球鼻重心高、球鼻长度、艉封板浸水面积、水线上横剖投影面积、侧推直径。
- `Appendages`：舭龙骨、Dome、减摇鳍、呆木面积；舵/桨数量。
- `Holtrop`：按所选方法补参数。
- `Calculate`；`Report`（fds）、`Export`（xls）。
- **注意单位**：m 还是 mm。

## 6. Stability Tree（完整稳性）

结构（详见 `fbasic-stability.md`）：

1. `Stability Criteria`：选规范/子条款（IMO IS Code 等）。
2. `Formula`：定义计算表达式。
3. `Loading Condition`：工况（空船+货物+压载+油水）。
4. `Group of loads`：装载组。
5. `Initial situations`：初始状态。
6. `Damages`：破损位置（可 `Generate Damages`，含 `MARPOL` 等破损范围）。
7. `Flooding`：确定法破舱校核。
8. `Max KG calculation`：极限重心高（类型可选 `Damage`，选初始状态/破损）。

### 6.1 装载工况 CLI（`foran fbasic lc`）

```bash
$S fbasic lc --db <db副本> --lsw LSW-02 [--load 32792,95,8]
```

流程：`Stability` 标签 → `Loading Conditions` 右键 `New loading condition` → 编辑器里双击 `LightShipWeight` 从下拉选 `--lsw` → 可选：`Local loads` 标签 → 绿色 `+` → 填写 `Weight / XCG / ZCG` → 单勾关闭编辑器 → 右键 `Loading Conditions` → `Calculate`（`LoaLoadCondRunPopUpCmd`，自动关 Progress/Error/Warning）→ `File > Save` → `File > Exit`（`Information modified` 选 Yes）。校验 `DSG_LOAD_COND.CALCULATED=1` 与 `DSG_LOCAL_LOAD`。

实测（`cli_lsw_test.db`）：`LC-0001 calculated=1 loads=[('LOA-0001', 32792, 95, 8)]`。

注意：

- 必须先有**已写库**的 LSW 分布；同一次 FBASIC 会话里 `Calculate`/`Update` 可能报 `LSW distribution not calculated`（缓存），重启后消失，不影响已保存结果。
- **编辑器控件全部按 UIA 结构定位（2026-10-28，不再依赖固定坐标）**：
  - `Local loads` 标签：`TabItem` 按名称点击。
  - 绿色 `+` / 红色 `-`：这两个图标按钮没有可访问名称，按“紧贴标签栏左侧、同一水平带”定位——取标签栏左边缘距离最近的两个空文本按钮，左边的是 `+`。
  - 单勾（接受/关闭）、双勾（应用）：树停靠区底部同一水平带的一排空文本按钮，最左边是单勾，第二个是双勾。
  - `LightShipWeight` 值单元格：按 `LightShipWeight` 标签行的右半格（TreeItem）定位；双击后下拉列表的 `ListItem` 暴露名称，按 `--lsw` 名称点击（比按序号偏移可靠，下拉顺序=DB 顺序，不一定是序号顺序）。
  - 校验：关闭前轮询重读 `LightShipWeight` 单元格，必须等于 `--lsw`。
  - `Save`/`Exit` 用 File 菜单的 UIA 名称点击（`_menu_key` 兼容 `&` 与 `\t` 快捷键后缀），坐标只作兜底。
  - 局部载荷行按数值校验（重量 0.5 t、XCG/ZCG 0.05 m 容差），支持小数输入。
- 右键菜单优先用 UIA `MenuItem` 名称点击（`_popup_pick`），坐标偏移仅作兜底。

## 7. 概率破舱（Probabilistic damage stability）

结构（详见 `fbasic-stability.md`）：

1. `Section Definition`：限界面（A/B/C 等）。
2. `Initial Situations`：初始状况。
3. `General Options`：基本信息。
4. `Regulation`：选校核规范。
5. `Subdivision Cases`：破损组合。

## 8. 结果与报告

- 大量计算都有三个出口：`Report`（.fds，FDM 打开）、`Export`（xlsx/xls）、`Plot/Drawing`（dxf/pdf）。
- `.fds` 用 FDM 看/打印；Excel 用于二次处理。
- 报告前确认：水密度、吃水、纵倾、渗透率、附体、板厚等设置一致，否则同一项目不同计算会对不上。

## 9. 常见坑

1. **没建水密船体**：所有静水力/稳性计算都缺基础。
2. **节点没锁**：命令灰掉或不能改。
3. **吃水/纵倾/水密度不一致**：不同计算之间结果不可比。
4. **渗透率**：舱室默认 95%，破舱/浸水要按规范改。
5. **干舷没算就做 MARPOL**：MARPOL 的 Ship data 依赖干舷结果。
6. **单位**：Power predict 等处 m/mm 混用会差 1000 倍。
7. **报告模板**：MARPOL 要选 `Mpl12A_doc.fpl` / `Mpl23_doc.fpl`。
8. **不同版本 vs V80R3.0**：字段名可能略有差异；以本机界面/帮助为准。

## 10. 自动化导航（脚本，2026-10-28）

`foran fbasic wh/hydro/cross/capacity/freeboard/tonnage/lsw/lc` 现在统一按 UIA 结构定位，不再依赖 1920×1080 的绝对坐标：

- **停靠标签**：`Entities` / `Calculations` / `Stability` 用 `TabItem` 名称点击（`_click_tab`）。
- **树节点**：按文本查找（`_tree_item_contains`），需要展开时点节点三角 + `Right`（`_expand_node`），只在子节点不可见时执行。
- **Tree view 不要重复创建**：`dsgnewndtree` 按钮每点一次会**新建一个 Tree view 停靠区**，挤占计算面板。`_ensure_tree` 现在先检查是否已有可见树（`Ship`/`Elements` 行），有则直接返回。
- **File > Save / Exit**：按菜单项名称点击（`_popup_pick`），坐标只作兜底。
- **计算面板行**：面板按需渲染，行在可见区域内才会出现在 UIA。`_wait_panel_row` 会轮询等待行出现；如果面板被停靠得很矮（行在可视区之外），UIA 看不到这些行——需要把 `... data edition` 面板拉高/最大化后再跑。
- **数值单元格**：`_set_row_value` / 横截曲线排水量现在点击 UIA 找到的值单元格中心，而不是固定 `x=450`。
- **回归（2026-10-28）**：`hydro`（58 行）、`cross`（357 行）、`capacity`（CT-0001，levels=15/spacing=1）、`freeboard`（FB-0001 data/results=1）、`tonnage`（TONN-0001）、`wh`（sections 69）全部 EXIT=0。
