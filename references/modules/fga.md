# FGA — 分舱与总布置（FORAN General Arrangement）

FGA 用来在 FORAN 项目库里定义舱室（Spaces）、型表面/舱壁/甲板的布置，并生成总布置图。它和 FBASIC 共享同一个项目库。

> 来源：实际操作经验整理。软件 V80R3.0；界面可能因版本略有差异；菜单名以下表为准，路径以实际界面为准。

## 目录

1. [启动与项目](#1-启动与项目)
2. [系统配置](#2-系统配置tools--properties)
3. [加载线型](#3-加载线型loading-surface)
4. [定义舱室](#4-定义舱室spaces)
5. [总布置图](#5-总布置图general-arrangement-drawing)
6. [数据输出](#6-数据输出)
7. [常见坑](#7-常见坑)
8. [脚本自动化（选库/树/GA/BREP）](#8-脚本自动化选库树gabrep)
9. [命令速查](#9-命令速查)

## 1. 启动与项目

```bash
S=foran
$S launch fga --project "<db>" --copy-project ".\_foran_work\projects"
```

- FGA 启动后弹 `Database settings`：
  - `Open DB file`：打开已有项目库（项目提供的 `.db`）。
  - 新建：在 `FNAM` 输入 **4 个英文字符**，选路径，生成 `<FNAM>.db`。
- 同一个项目库可被 FGA 和 FBASIC 同时/先后打开；不要两个模块同时写同一个库。
- 打开前先复制，避免 `Database is locked` / 改坏原件。

## 2. 系统配置（Tools > Properties）

### 2.1 General arrangement（出图设置）

- 字体高度/宽度：实际尺寸 = 设定值 × 出图比例。例：设定 2、Scale=100 → 实际 200。
- `Frame`：`Margin`（页边距）、`Seal height`（标题栏高）、`Seal width`（标题栏宽）。
- `Line width, style and color`：各类出图对象的线宽/线型/颜色。
- 横剖视图方向：`Looking from aft end`（艉→艏）或 `Looking from fore end`（艏→艉）。

### 2.2 Name pattern（命名规则）

选择对象类型 → 固定前缀（Fixed prefix）→ 可变序列号（如 001/002）→ 位数（Digits）。

### 2.3 Space definition（舱室默认参数）

| 参数 | 默认/说明 |
|---|---|
| `Displacement type` | `Standard` 主船壳内；`Negative` 减少排水量（海底门、侧推管）；`Appendage` 主船壳外水线下（呆木、舵）；`Space increasing the displacement` 主甲板以上上层建筑；`Timber deck` 原木甲板；`Hatch` 舱口盖（需关联货舱） |
| `Steel discount` | 结构扣除率，默认 2% |
| `Permeability` | 渗透率，默认 95% |
| `Loads` / `Types` | 默认装载对象/舱室类型，一般留空 |

### 2.4 Tessellation（网格精度）

`Precision level` 1–5；级别越高越精确、文件越大。`surface tolerance` / `Boundary tolerance` 随级别自动变，也可 `Custom` 手改。

### 2.5 Transparency（透明度）

选 `Surface type name` → `Display` 选 `Shade` → 拖 `Transparency`。外层透明后可看到内部舱室。

### 2.6 Tree / Units / 2D spaces environment

- `Show trees` 控制左侧选项卡显示。
- 单位：长度/角度/重量。
- 2D 环境：肋位编号间隔、数字对齐（bottom/top、left/centre/right）、标记位置/高度（Normal / With number）。

## 3. 加载线型（Loading Surface）

### 3.1 加载 FSURF 文件（`.fsf`）

命令：`File > Import > Hull forms`

1. 在 `Surface` 选项卡右键 `Ship` 节点 → `Lock`。
2. 选 `.fsf` 文件。
3. `Edit` 编辑加载对象：
   - 左侧列表勾选要加载的对象；`Name` / `Description` / `Location` / `Symmetric of`。
   - `PREVIEW` 预览（蓝色）。
4. 肋位系统：
   - 勾 `Import frame system` 直接读型线文件里的肋位。
   - 不勾则手填 `Frame number`、`Abscissa`、`Orientation`（`EUR` 艉→艏；`USA` 艏→艉）。
   - `Spacing`：`Add/Edit/Remove`，`Last frame`、`Spacing (m)`。
5. `Show summary` 核对 → `OK`。
6. 对象出现在 `Surface` 选项卡，拖到工作区查看。

**自动导入（2026-10-27 实测）**：

```bash
S=foran
$S fga import-hull --db <sample.db> --fsf TESTfsurf.fsf --copy
```

流程：FGA 启动 → `SrfCmdImportFormsFile` → 选 `.fsf` → `Import surfaces` 点 `OK` → 若已有同名 `External hull`，弹覆盖确认 → 选 `Yes to All` → `File > Save`。实测把示例 40 个 patch 替换成生成的 11 个 patch（`DSG_GSF_TREE` TYPE=4 行数 40→11）。

**导入会删除 External hull 的全部子线**（含 PROFILE 线 `CL`），FBASIC 之后每次启动都会提示 `The ship's profile is not defined`。命令现在会在导入前快照这些线（`DSG_GSF_TREE` / `DSG_LINE_DATA` / `DSG_WIRE_DIR` / `DSG_TREE_USER_DATE`），保存并关闭 FGA 后回填；`--no-restore-lines` 可关闭该行为。实测 10 条线全部恢复（`CL` 类型 4），FBASIC 启动 110 s 无警告。

注意：

- `Import surfaces` 的 Surfaces 区是自绘列表（`New / Edit / Preview`），UIA 无法枚举；如果 FSF 里的表面已带好 Location（`/Ship`），**不需要点 Edit**，直接 OK 即可。
- 导入会**替换**项目里同名表面的 patch；务必在数据库副本上做。
- 新 hull 与旧线几何差异很大时，回填的旧线不一定匹配（尤其 `BULWALK`/`DECK_INTER`）；可先 `--no-restore-lines`，再在 FSURF/FGA 里重建线。
- 如果导入的是**开放壳**（例如 `hull gen` 的 `makeSolid=False` 壳），FGA 表面能导入，但 FBASIC `Build WH` 可能无法闭合成实体，且会删掉原来的主船体实体。需要闭合壳（带甲板/端封）或改用其他方法。

### 3.2 加载 IGS/STP（外部格式）

1. 选 `.igs` / `.stp`。
2. `Edit`：`Name`、`Description`、`Location`、`Type`（外船壳/内船壳/甲板/舱壁）、`Patches`（用中间箭头选择）。
3. **不要勾 `Import frame system`**；手动定义 `Frame number`、`Abscissa`、`Orientation`。
4. 用 `Add/Edit/Remove` 定义肋距。
5. `OK` 加载。

## 4. 定义舱室（Spaces）

### 4.1 舱室属性

命令：`Spaces > New Space` 或右键弹出菜单。

| 字段 | 说明 |
|---|---|
| `Name` | 舱室名，建议英文 ≤8 字符 |
| `Description` | 描述，可用中文，≤50 字符 |
| `With symmetric` | 同时生成对称舱室，名称自动加后缀 `S` |
| `Cargo tank` | 液货舱；自由液面修正时可按倾斜角/装载率计算 |
| `Space types` | 预定义舱室类型 |
| `Freeboard type` | 干舷计算用的舱室类型 |
| `Displacement type` | 排水量类型（默认取系统设置） |
| `Steel discount` | 结构扣除率（默认 2%） |
| `Permeability` | 渗透率（默认 95%） |
| `Loads` | 装载对象，可多选 |
| `Candidates` | 候选舱室；新舱室属性全部复制，每个候选只能用一次 |

底部图标：保存并退出 / 保存并继续新建 / 保存并复制 / 取消 / 合并多个子舱室。

### 4.2 由 6 个限界面定义（6 limits）

舱室可由多个 `Subspace` 组成；`+` 增加、`-` 删除。

6 个面：`aft`, `fore`, `starboard`, `port`, `bottom`, `top`。每个面可以是：

- 已加载的型表面（外船壳、甲板等）：输入名字或在工作区点选；
- 绝对坐标平面：`x20.4`（横剖面）、`y10.5`（纵剖面）、`z4.2`（水平面）；
- 肋位坐标：`FR20+0.2`。

自动捕捉：点自动捕捉图标 → 在舱室内部点一下 → 系统捕捉 6 个边界。`Extern option` 允许超出外船壳。点生成图标建模型。

### 4.3 由一组型表面定义（a set of surfaces）

1. 手动输入/点选围成舱室的型表面。
2. 自动捕捉：点图标 → 舱室内部点一下。
3. 生成模型。
4. 若型表面组合有多个方案，从下拉列表选 `Option 1/2/...`。

加载新型表面：`File > Import > Hull forms`。

### 4.4 导入外部舱室模型

- 支持 `IGES` / `STEP` / `BREP`：导入其他软件模型作为 FORAN 舱室。
- 导入后可在树上查看/编辑。

### 4.5 参数化舱室（Parametric spaces）

- `Type`：`cylinder`、`truncated cone`、`crown sector`。
- `Orientation`：`longitudinal`、`vertical`、`transversal`。
- `U axis` / `V axis`：中心轴坐标；`start`/`end`：始末端位置。
- 封盖参数：点展开图标按示意图输入。
- `Attributes`：特殊属性。
- 生成图标建模型。
- 典型用途：侧推筒、管隧、圆柱形压载舱。

### 4.6 复杂舱室 / 负舱室

1. 复制已有舱室：右键 `Copy` → 选舱室 → 得到子舱室列表。
2. 在 `Summary` 选项卡勾 `negative`：该舱室体积从总体积中扣除。
3. `Summary` 显示各子舱室体积、重量、重心。
4. 结果：复杂形状 = 外包舱室 − 负舱室。

### 4.7 从 VOLUME 模块导入舱室

命令：`File > Import > Spaces > Volume spaces`

1. 选 VOLUME 生成的 `FNAMcomps.fil`。
2. 若有舱室无法计算，系统给警告。
3. `Edit`：改 `Name`/`Description`，选存放路径。
4. 重新计算选项：
   - `YES`：读取数据并重新计算舱室模型；
   - `No`：只读数据，不计算。
5. 导入后右键舱室 → `Recalculate` 可重算。
6. 图标含义：
   - 正常舱室；
   - 对称生成（只能改属性，几何要改原舱室）；
   - 几何无法计算（检查边界后 `Recalculate`）。

### 4.8 编辑舱室

命令：`Spaces > Edit Space` 或右键。对话框与新建类似：`Property` 改属性，`Geometry` 改边界/子舱室。

### 4.9 导出舱室模型

选要导出的舱室（勾选）→ 选路径/格式/文件名 → 保存。用于给其他软件或后续计算。

### 4.10 干涉检查

命令：`Spaces > Interferences`

- `Group A` 选被检查舱室，`Group B` 勾其他舱室；两两比较。
- `Testing Mode`：`Interferences`（只查干涉）或 `Interferences + contacts`（含接触）。
- `Display`：`bounding boxes`（边界盒）或 `own spaces`（实际模型）。
- 结果列表里选一组，模型自动显示在工作区。

## 5. 总布置图（General Arrangement Drawing）

### 5.1 出图配置

`Tools > Properties`：字体、图框（Margin/Seal height/Seal width）、线宽/线型/颜色（同 2.1）。

### 5.2 新建图纸与视图

1. 在 `General Arrangement` 选项卡右键 `Ship` → `New drawing`。
2. `Draw Option`：
   - `Name`、`Description`；
   - `Paper Size`；
   - `Portrait` / `Landscape`；
   - `Scale`；
   - `Frame number interval`（每隔几档肋位显示数字）。
3. `Views Option` 添加视图：
   - `Plan`（水平面）：输入高度（如 `1000mm`）剖切，或选下/上甲板生成两层甲板间投影；
   - `Side`（纵剖）：输入 Y 坐标得剖视，否则右舷投影；
   - `Transv.`（横剖）：输入横剖面位置。
4. 每个视图可设甲板、舱壁、舱室的线宽/线型/颜色；舱室可用 `Space type` / `Load type` 过滤。

### 5.3 生成图纸

1. 右键图纸名 → `Arrange drawing`：按视图位置切模型，自动生成图纸。
2. 右键 → `Open drawing`：在 2D 环境打开。
   - 中间图纸区；顶部工具条画线/圆/编辑；
   - `Layers`：图层 0/1/2/3 系统专用，**用户对象必须放图层 4**，否则重新 `Arrange drawing` 会被删；
   - `Blocks`、`Properties`、`Libraries`（用户图库，dxf/e2，可拖入）。

### 5.4 完善图纸

- 插入图框：右键空白 → `Insert/Change frame` → 选模板。
- 插入主尺度：右键 → `Insert main particulars` → 选模板。
- 插入舱室汇总表：右键 → `Insert capacities table` → 图面选插入点。

## 6. 数据输出

| 命令 | 输出 |
|---|---|
| `File > Spaces to spreadsheet` | 舱室列表（可选过滤条件，如 Load type）→ 电子表格 |
| 打开 FGA 图纸 → `File > Save as` | 布置图（选路径/格式） |
| `Custom > Space report` | 所有舱室信息汇总报告预览，可导出多种格式 |

## 7. 常见坑

1. **节点没锁**：新建/编辑前先右键 `Ship` 节点 `Lock`，否则命令灰掉或改不了。
2. **6 限界面选错**：面名/坐标/肋位三种写法混用；生成前用 `Summary` 核对体积。
3. **对称舱室**：几何只能改原舱室；改对称舱室无效。
4. **负舱室**：勾 `negative` 后体积才扣；别忘了 `Summary` 核对。
5. **2D 图层**：用户对象放图层 4；放错会在 `Arrange drawing` 后消失。
6. **重新出图会覆盖用户图元**：先确认图层/图库，重要图元放图库或导出。
7. **库锁**：FGA/FBASIC 不要同时写同一个库；先复制。
8. **不同版本 vs V80R3.0**：菜单文字可能略有差异，以本机界面为准；命令名可查 `references/modules/` 或模块的 Help 菜单。

## 8. 脚本自动化（选库/树/GA/BREP）

FGA 的启动顺序和 FSURF 不同：**先选项目库，再加载项目**。因此脚本里要读舱室/出图，必须先让 `Database settings` 选好库；`foran fga ... --db <db>` 会自动完成这一步。

```bash
S=foran

# 导出舱室（sample 库当前没有舱室，只出表头）
$S fga spaces --db "D:/.../sample.db" --out out/spaces.tsv --copy

# 导出设计树（GspView/GsfView/CmpView；示例库 49 节点）
$S fga tree --db "D:/.../sample.db" --out out/tree.tsv --copy

# 一次启动同时导出舱室 + 树（省一次 FGA 启动）
$S fga export --db "D:/.../sample.db" --spaces out/spaces.tsv --tree out/tree.tsv --copy

# 创建 GA 布置图 + 三视图 + Arrange + DXF + 存库
$S fga draw --db "D:/.../sample.db" --out out/GA.dxf --copy
```

实测结果（`sample.db` 副本）：

```text
fga spaces : 0 个舱室（只有表头）
fga tree   : 49 个节点 = 1 曲面 + 45 Patch + 3 甲板
fga draw   : DXF 394,634 B；1134 LINE / 28 LWPOLYLINE / 58 MTEXT
             DSG_GA_TREE 5 行；4 张 GA 数据表各 1 行；DSG_GA_VIEW_ELEMENTS 6 行
```

对应的数据库表：

| 表 | 作用 |
|---|---|
| `DSG_SPC_TREE` | 舱室树（示例库只有 Ship/HULL 根节点） |
| `DSG_GSF_TREE` | 型表面/甲板/Patch 树（示例库 63 行） |
| `DSG_GA_TREE` | GA 图纸树（Ship → 图纸 → Plan/Side/Transv 视图） |
| `DSG_GA_DRAW_DATA` | 图纸头（名称/纸型/比例） |
| `DSG_GA_{PLAN,SIDE,TRANSV}_VIEW_DATA` | 各视图参数 |
| `DSG_GA_VIEW_ELEMENTS` | 视图内元素 |

注意：

- `GaNewDrawCmd` / `GaArrangeDrawCmd` 需要 GUI 树里已有选中项；`fga draw` 用 UIA/坐标代点完成选中。
- 2D 绘图环境的 `File > Save as` 只导出 DXF/SVG/e2/CXF；`File > Save drawing` 才把图纸写回项目库。
- 坐标按 1920×1080 最大化窗口测量；换分辨率需重新量。
- **2026-10-28 更新（BREP 导入链路）**：`Import spaces file` 对话框是 Qt 自绘 QWidget，但控件可枚举——`Files of type` 通过旁边的 `Files of type:` 标签找到同一行的 ComboBox 再点击（不再用固定 `(960,712)`）；文件按 `ListItem` 名称点击；`Open` 按按钮名称点击。项目保存改为 File 菜单按 UIA 名称 `Save`（坐标兜底）。实测 `--box 3,3,3` → `SPC-0006`。
- 导入前确认没有其他 FORAN 模块占着目标副本，否则 FGA 提交时报 `database is locked`（见 `troubleshooting.md`）。

### 8.1 新建舱室（2026-10-26 半自动实测，未完全打通）

新建舱室的完整 GUI 流程已经摸清，但“建模”一步仍有坑：

1. **锁定项目/树**：右键根节点 `Ship` 选 `Lock`；锁好后该项菜单第一项变成 `Unlock`。
2. **选中目标节点并 Set active**：右键节点（如 `CARGO`）→ `Set active`。
3. **New space**：右键激活节点 → `New space`（或菜单 `Spaces > New space`）。
   - 未锁定/未激活时只会报 `Invalid item selected`。
4. **Space definition 面板**（docked 在窗口底部）出现：
   - 空间级按钮：保存并退出（绿勾）、保存并新建、保存并复制、取消（红 X）、Build、用户属性。
   - 子舱室级按钮：显示/隐藏属性、增加子舱室（绿 +）、删除、从树复制、对称复制、自动捕捉。
5. **Six limits** 页：点绿 + 增加一行 `SUBSPC-0001`；双击单元格进入编辑，输入后回车。
   - 单元格接受纯数字：输入 `50` 会解析成 `x 50.000`；输入 `3` 解析成 `y 3.000 m`；`2` → `z 2.000 m`。
   - 也接受型表面名（如 `External hull`、`MDeck`）和肋位语法 `FR n`。
   - **坑 1**：`pyautogui.typewrite("X 50")` 会丢掉空格变成 `X50`，被拒绝；要么只输数字，要么用剪贴板粘贴带空格的表面名。
   - **坑 2（重要）**：表格列坐标取决于左侧属性树是否显示。属性树可见时（默认），表格从 x≈423 开始：Aft 630、Fore 730、Starboard 830、Port 930、Bottom 1030、Top 1130、Model 1285；属性树隐藏时表格从 x=0 开始，列位置整体左移。**按错列会把值写进属性树/相邻列**，之前多次 `Model` 失败就是这个原因。
6. **Six limits 仍然失败**：即使六格都按正确列填入，`Model` / `Build space` 仍报 `Error modeling subspace` / `Recalculation of subspace(s) SUBSPC-0001 failed`。已试过：
   - 纯平面盒：x=50..100 / y=±8 / z=2..10；x=50..80 / y=±4 / z=2..10；x=40..60 / y=±3 / z=2..8。
   - 宽盒（让外船壳裁剪）：x=50..80 / y=±20 / z=0..10。
   - 上下限用型表面：Bottom=`External hull`、Top=`MDeck`，侧限 x=50..80、y=±4 或 y=±20。
   - 把 `External hull` 拖进 3D 场景显示后再点 Model；均失败。
   - CARGO 节点是 `GsNodeTypeEnum.GsNodeWorkArea=2`，父节点类型合法。
   - **重要线索 1**：Surfaces 选项卡 → 右键 `External hull` → `Patches orientation` 打开 `Analyzer`，船体上半部红色、下半部绿色。FGA 帮助要求型表面 **uniform-oriented and continuous**；但红色/绿色也可能只是前/背面着色，不能单独作为朝向错误的结论。
   - **重要线索 2（更关键）**：右键 `External hull` → `Shape analyzer` → 勾 `Free edges` / `Overlapped edges` → `Analyze`，结果列表：
     - `SHELL > Free edges > WIRE > Closed wire`（点选后青色高亮出现在**船体顶部的甲板开口边**）；
     - `Overlapped edges > GROUP OF SHAPES > Overlapped edges`。
     - `Fix shape` 后再 `Analyze`，这两项**仍然存在**。
     - 对 `Ship` 根节点直接跑 `Shape analyzer` 返回**空错误列表**（根节点不是 surface）；必须先选中具体 surface（如 `External hull`）再分析。把整船拖进场景后分析根节点仍然是空列表。
   - **Surfaces set 也不行**：在 `Surfaces set` 页加一行，Limit1=`External hull`、Limit2=`MDeck`，点 Model 不报错但 Summary 的 volume 是 **0.000**。说明只有 hull+deck 两个面不足以围成实体，还需要横/纵舱壁或封闭端面（transom）。
   - 结论：外船壳是**开放壳**（顶部是甲板开口的 closed wire），它和 MDeck 等甲板面没有缝合成封闭实体；六限界/两曲面 set 的布尔裁剪都无法得到体积。下一步不是继续调六限界坐标，而是：在 FSURF 里补/缝 hull+deck+横舱壁/transom 成封闭模型，再重新导入 FGA；或者继续用参数化子舱室。
7. **参数化子舱室可以成功建模**（已实测）：
   - `Parametric` 选项卡 → 绿 + → 默认 `Cylinder`/`Longitudinal`；
   - 设 Axis U(y)=0、Axis V(z)=5、Start(x)=50、End(x)=80、Radius=1；
   - 点行内 `Model`（x≈1235）→ 场景出现圆柱，无报错；
   - `Save and Exit` → 关闭 FGA 时选 `Yes` 保存项目；
   - 数据库出现 `SPC-0001`（TYPE=7）、`SUBSPC-0002`（TYPE=24）、`LIM-0001`（TYPE=25）；
   - `foran fga spaces` 导出：volume=94.2477836618（=π·1²·30）、COG=(65, ~0, 5)、bbox x=50..80 / y=-1..1 / z=4..6，完全正确。
   - 说明：**空间/节点/项目设置没问题，问题只在“六限界”这条几何路径**。
8. **自动捕捉**：先把型表面拖到 3D 场景（从 `Surfaces` 选项卡把 `External hull` 拖进视图），点自动捕捉图标，再在船体内部点一下。实测会把 `Aft` 填成 `External hull`，并把焦点移到 `Fore`，后续需要继续点选/输入；没有一次走完。

坐标参考（sample）：

- `DSG_SOLID_HULL_SECTIONS.X` 范围约 **-3.2 .. 176.5 m**；
- 肋位表 `DSG_FRAME_LIST`：`NUM_FR` -99..126，`ABS_FR` -65.34..99.4 m；
- 三套数值不是同一个原点，写限界面时不要混用。
- `GsNodeTypeEnum`：Root=1、WorkArea=2、Group=3、SubGroup=4、Deck=5、DeckWrkArea=6、Space=7、Reserve=8……
- `GsLimitsDefsEnum`：Surf=1、SurfDist=2、Fr=3、X=4、Y=5、Z=6、GenPlane=7。

> 结论：**参数化子舱室**已验证可建模、保存并用 `fga spaces` 正确导出（体积/重心/包围盒都对）；**六限界**路径因船体表面朝向/连续性问题仍然失败，需先修 `Patches orientation` 或重导船体。暂不提供 `foran fga newspace` 一键命令；手动建模后 `fga spaces` 可正常导出。

### 8.2 用 BREP/STEP 导入闭合舱室（2026-10-26 实测，推荐绕过开放壳）

FGA 的 `Imported` 子舱室支持 **IGES / STEP / BREP**，文件里必须至少有一个 solid。这样可以把任意 CAD 建好的闭合实体直接变成 FGA 舱室，不依赖六限界，也不受 sample 开放壳影响。

流程：

1. 生成 BREP。例如用 `gmsh`（已装进 `.venv`）：
   ```python
   import gmsh
   gmsh.initialize(); gmsh.model.add("box")
   gmsh.model.occ.addBox(0, 0, 0, 20, 10, 8)
   gmsh.model.occ.synchronize()
   gmsh.write(r"/path/to/box.brep")
   gmsh.finalize()
   ```
2. FGA 启动（锁树）→ 选中目标 node → `Set active` → `New space`。
3. `Space definition` → **Imported** 页 → 绿色 `+` → `Import spaces file`。
4. `Files of type` 选 **BREP file (*.brep)**（或 STEP/IGES）；**点文件列表里的文件**（只把全路径填到 File name 会让 Open 变灰）；`Open`。
5. `Summary` 页核对 volume/COG → `Save and Exit` → 关闭 FGA 时选 `Yes` 保存项目。
6. `foran fga spaces` 导出。

实测（20×10×8 m box）：

```text
volume = 1600.000 m³
COG    = (10, 5, 4)
bbox   = x 0..20 / y 0..10 / z 0..8
area   = 880 m²（= 2·(20·10+20·8+10·8)，正确）
```

这是目前**最可靠的闭合舱室路径**：任意 CAD/脚本生成的封闭实体（货舱、压载舱、设备包围体）都可以 STEP/BREP 导入。六限界仍适合在“有完整封闭船体+舱壁”的模型上使用。

一键版本（`foran fga brep`）：

```bash
# 导入现成 BREP/STEP/IGES
$S fga brep --db "D:/.../sample.db" --brep box.brep --node CARGO --copy

# 用 gmsh 生成 box 再导入：L,W,H[,X,Y,Z]
$S fga brep --db "D:/.../sample.db" --box 20,10,8 --node CARGO --copy
```

实测（自动流程，2026-10-26）：

```text
--box 20,10,8 -> SPC-0002, volume 1600.000, COG (10,5,4), area 880
--box 5,5,5   -> SPC-0003, volume 125.000,  COG (2.5,2.5,2.5), area 150
--box 3,3,3   -> SPC-0003, volume 27.000,   COG (1.5,1.5,1.5), area 54
```

命令会自己完成锁树、Set active、New space、Imported 文件选择、Save and Exit、保存项目，并打印新舱室名/OID。

### 8.2 六限界最终结论（2026-10-27）

- **开放壳**（11 patch）：`Recalculation of subspace(s) ... failed`。
- **闭合 IGES**（hull.igs，77 patch）：`Shape analyzer` 仍有 2 个 `Free edges → Closed wire`；`Fix shape` 容差 0.0005/0.01/0.1 都补不上。
- **FSURF 13 面闭合壳**（11 侧面 + 艏艉封盖 → `foran fsf build` → FSF → FGA import-hull）：FGA 里只有 11 patch，但 **无 Free edges**，只报 `Overlapped edges`；`Fix shape` 无法消除。
- 六限界行填对（数据行 **y≈793–822**；Aft x≈589–688；`x50–80 / y±4 / z2–8`）后，`Build Space` 仍报 `Recalculation failed`；尝试 `Extern` 列也无效。
- 结论：六限界被 FORAN 的 patch 重叠/重算逻辑卡住，不是缺端面；继续调坐标/容差收益低。**替代方案**：参数化子舱室、`foran fga brep` 导入 BREP/STEP/IGES 实体。

## 9. 命令速查

按功能分组的命令表包括：

- 文件/视图/属性、导入导出；
- 2D 定义环境（Working Deck/Area、肋位、标签、轮廓）；
- 舱室与子舱室几何命令；
- GA 图纸命令；
- 2D 绘图工具；
- Tools/Standards；
- 三条典型工作流（3D 建舱室、2D 建舱室、生成 GA 图）。

### 8.2 空间面板按钮（2026-10-28）

- `New space` 之后的空间定义面板有一排无名称的 QToolButton：`Save & Exit` 是整行最左边的图标，`Imported` 页的绿色 `+` 是面板组里第一个绿色图标。
- `cmd_brep` 现在按结构定位：先找 `Summary/Six limits/Surfaces set/Imported/Parametric` 标签栏，取标签栏上方 30 px 内的空文本按钮；最左为 `Save & Exit`，面板组内用像素颜色找绿色 `+`。
- UIA 失败时才回退到旧坐标 `(14,710)` / `(470,710)`，并打印提示。
- 回归：`fga brep --box 5,5,5` → `SPC-0011`，EXIT=0，无回退告警。

### 8.3 总布置图自动化（2026-10-28）

- `Tools` 菜单项可枚举：`New node / Edit node / Delete node / New drawing / Edit drawing / Delete drawing / Open drawing / Arrange drawing / Rearrange items`。
- 菜单栏本身仍用坐标打开（`(482,65)` 相对窗口），但 `New drawing` / `Arrange drawing` 已按 UIA 名称点击。
- `Ship` 根节点与新建的图纸行都按 TreeItem 名称选择；图纸名取对话框里的实际值（如 `DRAW-0002`）。
- 2D 上下文里的 `Save as / Save drawing / Exit 2D context` 也改为按 UIA 名称点击，并使用 `popup_first=True`（同名菜单项优先取当前打开的 QPopup，避免命中主窗口的隐藏项）。
- 只有“打开菜单栏”这一步仍用窗口相对坐标（`_menu(G, win, x, y)`）；FGA 里 UIA 直接点菜单栏不可靠。
- 实测（sample 副本）：DXF 394,605 B，EXIT=0。
- **常见失败**：`The surfaces tree hasn't the information about the contour lines`——该库没有型表面轮廓信息（例如只有吨位数据的副本），GA 图无法生成；换带船体表面的库（如 sample）。
