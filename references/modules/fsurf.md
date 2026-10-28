# FSURF — 型线/曲面建模（FORAN Surface）

FSURF 负责船体型线：点 → 多段线 → 曲线 → 曲面（Patch）→ 光顺 → 特征线/结构 → Build Ship → 肋位/甲板/舱壁。它是 FGA/FBASIC 的上游；`Build Ship` 生成的 `FNAMfsurf.fsf` 会被 FGA 作为 `Hull forms` 加载。

> 来源：实际操作经验整理。软件版本 V80R3.0；界面可能因版本略有差异。

## 1. 启动

```bash
S=foran
$S launch fsurf --workdir ".\_foran_work\fsurf"
```

- 不需要项目库；启动后直接进主界面（标题含 许可信息 说明许可正常）。
- 工作目录决定 `.fsf/.pnt/.pol` 等相对路径文件的位置。

## 2. 视图与选择（实测）

| 操作 | 鼠标/键 |
|---|---|
| 框选放大 | 按住右键拉框 |
| 缩放 | 滚轮；`Shift + 左键` 上下拖 |
| 平移 | `Ctrl + 左键`；鼠标中键 |
| 旋转 | 左键绕默认中心；双击对象设新中心 |
| 满屏 | `F2` |
| 选择对象 | `Shift + 左键` 框选；`Shift + 单击` 逐个 |
| 取消选择 | `Ctrl + 左键` 框选；`Ctrl + 单击` 逐个 |
| 全选/全不选 | `Alt + S` / `Alt + A`（部分模块） |

> 以上快捷键来自实测，标注“部分模块”；以实际界面为准。

## 3. 建模主流程

```text
点(.pnt) → 多段线(.pol) → 曲线(.cur/.igs) → 光顺
   → 划分 Patch 边界 → 生成 Patch（近似/插值/边界/修剪）
   → 整体光顺 → 检查连接孔 + 法向
   → 特征线（Profile/SIDE/BOTTOM）→ Structure Manager
   → Build Ship（FNAM + 主尺度）→ .fsf
   → 肋位系统 / 甲板 / 舱壁
```

### 3.1 数据导入

- 点：`*.pnt`（ASCII）。
- 多段线：`*.pol`（ASCII）。
- 曲线：`*.cur` 或 `*.igs`。
- 曲面/全部实体：`*.fsf`（FORAN form file）。
- 也可 `File > Import` 导入 IGES/STEP/DXF 等（见帮助 `Import`）。

### 3.2 生成 Patch

| 方法 | 含义 | 适用 |
|---|---|---|
| `By approximation` | Patch 近似扫过曲线，允许微小偏移以优化光顺 | 复杂曲度，推荐 |
| `By interpolation` | 严格通过曲线 | 简单/精确通过点，不建议复杂区 |
| `By limits` | 由 4 条或 2 条边界曲线生成 | 平面/单曲 Patch |
| `By trimmed limits` | 边界不必首尾相连，系统求交 | 修剪边界 |

生成底平面/边平面：`Edit > Copy > Plane Scale`，选边界曲线，投影平面（如 `Y=0` 或 `Z=14`），比例因子 0。

### 3.3 检查

- 连接孔：`View > Visibility > Show > Holes between patches`，确保 Patch 间无缝。
- 法向：外壳“里红外绿”；内壳相反。**法向错会导致静水力计算错误**。

### 3.4 特征线与结构

- `Structure > Line > New line`：
  - 必须建 `Profile` 类型的中纵剖线；
  - 可选 `SIDE`（平边）、`BOTTOM`（平底）、折角线；
  - 不要建 `NONE` / `ORDINANRAY` 类型。
- `Structure > Manager`：把外壳 Patch 拖到 `External hull`，特征线拖到 `SURFACE LINE`。

### 3.5 Build Ship

命令：`File > Ship > Build Ship`（或 `Ship > Build Ship`）。

| 区域 | 字段 | 说明 |
|---|---|---|
| General | `FNAM` | **4 个字母数字**，船型文件名 `<FNAM>fsurf.fsf` |
| General | `Description` / `Project` / `Building` | 打印/图纸抬头 |
| General | `Type of ship` / `Classification Society` / `Owner` / `Deadweight` | 信息性 |
| Geometric | `Length between perpendiculars` | **必填** |
| Geometric | `Design breadth` | **必填** |
| Geometric | `Design draught` | **必填** |
| Geometric | `Design depth` | **必填** |
| Geometric | `Symmetric key` | 每个外板 Patch 的控制点严格只在一侧时勾选；跨舷 Patch 不勾 |
| Geometric | `Cylindrical body` | 平行中体起点（自 AP）+ 长度；无则填 0 |
| Geometric | `Max dimensions defined by user` | 默认自动；可自定义包围盒，`Calculate` 恢复自动 |

> `FNAM` 会直接决定 `FNAMfsurf.fsf` 的名字；FGA 加载、FBASIC 计算都靠它。示例里常用 4 字符如 `TEST`。

**自动填字段（2026-10-26 实测）**：`foran draw --build-ship --build-lpp 171 --build-breadth 29 --build-draught 9.5 --build-depth 14.8` 会在点 OK 前按 UIA 标签定位 Build Ship 的 Edit 并写入（click + ctrl+A + 剪贴板 + Tab）。任意字段用 `--build-field "Xmin=0"`。这些 Qt Edit 不支持 `set_edit_text`/`SetValue`。

### 3.6 肋位/甲板/舱壁

- 肋位：`File > Ship > Edit frame system`（实测路径）。
- 甲板：`Structure > Decks > New Deck`。
  - 甲板 ID 1–75；特殊 ID：`1` 主甲板、`9` 双层底、`10` 上边舱、`11` 首楼、`12` 桥楼、`13` 尾楼。
  - 定义方式：`Parametric` / `Non Parametric`；输入 ID、名称、类型、描述、限界。
- 舱壁：`Structure > Bulkheads > New Bulkhead`。
  - ID 1–999；方向 `General` / `Transversal` / `Longitudinal`。
  - 几何：平面、方向拉伸、槽形舱壁、按迹线（by traces）。
  - 横舱壁不需要对称设置。

## 4. 船型变换（示例重点）

### 4.1 Plane Scale（单向缩放）

命令：`Edition > Transform > Plane Scale`（或 `Copy > Plane Scale`）。

1. 选对象（如整个 hulls）。
2. 选基准平面（`X=0`、`Y=0`、`Z=K`）。
3. 输入比例因子。

| 变换 | 基准平面 | 比例 |
|---|---|---|
| 船长 | `X=0`（AP 不动） | 新 Lpp / 原 Lpp |
| 船宽 | `Y=0`（中纵剖不动） | 新 B / 原 B |
| 吃水 | `Z=K`（基线或指定水线） | 新 T / 原 T |
| 型深 | `Z=K` | 新 D / 原 D |

> 原理：每个点到基准平面的最小向量乘以比例因子。线性缩放后 Cb 不变。

### 4.2 Line Scale（双向缩放）

命令：`Edition > Transform > Line Scale`。

- 以一条线为基准，对垂直于该线的两个方向同时缩放。
- 步骤：选对象 → 选基准线 → 输入比例因子。

### 4.3 Plane Sliding（平面滑移/改纵倾）

命令：`Edition > Transform > Plane Sliding`。

- 定义平面 + 向量 + 比例因子；常用“平行于肋位的平面 + Z 方向向量 + tan(纵倾角)”改纵倾。
- 适合调整设计纵倾，不改变型线形状。

> 示例里的“新船长/船宽/吃水”变换通常用 **Plane Scale**；`Line Scale` 用于沿某线两个方向同时缩放。

### 4.4 LCB 变换

命令：`File > Ship > Ship transformations > LCB transformation`

| 参数 | 说明 |
|---|---|
| `HCG (%)` | 横剖面积曲线中心高度占最大值的百分比 |
| `Present LCB (m)` | 当前浮心纵向位置（距船中，向尾为正） |
| `New LCB (m)` | 目标值（距船中，向尾为正） |
| `INTERNAL HULLS` | 需同步变换的内船壳 |
| `Preview` | 预览新横剖面积曲线（红色） |

点 `OK` 迭代，最多 20 次；达不到目标会停下并列出最后值，让你接受或重输。

### 4.5 Cb 变换

**方法一：`Cb Transformation`**（适合增大 Cb）

命令：`File > Ship > Ship transformations > Cb transformation`

参数：`CM`（当前中横剖面系数）、`Current Cb`、`New Cb`、`INTERNAL HULLS`。迭代最多 20 次。

**方法二：`Quadratic Transformation`**（增大/减小都可）

命令：`File > Ship > Ship transformations > Quadratic Transformation`

参数：`HYDROSTATIC DATA`（当前 LCB/CM/Cb）、`New Cb`、`Modify zone`（后半体/前半体/两者，输入 `aft limit`/`Fore limit`）。迭代最多 20 次。

> 示例经验：**减小 Cb 用 Quadratic**；`Cb Transformation` 更适合增大。

### 4.6 横剖面积曲线编辑（Area Curve Edition）

命令：`File > Ship > Ship transformations > Area Curve Edition`

- 原理：直接改横剖面积曲线生成新线型；新曲线要与老曲线相似。
- 球鼻艏区域通常不可改（保证面积）。
- `Original data` 显示当前 Cb/LCB。
- `Transformation method`：`Automatic` / `Interactive`。
- `Zones to Modify`：尾部/首部/两者。
- 曲线：灰色=老曲线，黄色=新曲线；Y 轴为相对最大横剖面积百分比，X 轴为 20 站。
- 控制点：拖动红色点，或输入百分比；`Add`/`Delete`/`Clear`。
- 编辑时动态显示新 Cb/LCB；`OK` 后迭代，`Automatic` 达到目标自动停。

### 4.7 变换前后必做

1. **变换前删除老甲板/舱壁**（它们不会跟着型线正确变形）。
2. 变换后**重新定义**甲板/舱壁。
3. **重新 `Build Ship`**，更新 `FNAMfsurf.fsf`；否则 FGA/FBASIC 读到的还是旧线型。
4. 重新检查连接孔、法向、主尺度。

## 5. 型线图输出（Lines Drawing）

命令：`File > Ship > Drawings > Lines Drawing`

主要设置：

| 设置 | 说明 |
|---|---|
| `Scale` | 出图比例 |
| `File Name` | 输出路径/文件名/类型 |
| `Type of lines drawing` | `After - Fore` 前后半船；`After` 后半；`Fore` 前半；`Two drawings` 前后分开 |
| `Location of the body` | 侧视图放 `Centre` 或 `Right` |
| `Marks in the axis` | X 轴用 `Frames`（肋位）或 `Meters`（米） |
| `Marks for the parallel body` | 标出平行中体 |
| `Printing of main particulars` | 显示主尺度 |
| `Scale for the diagonals` | 斜剖图是否同比例 |
| `Drawing of special lines` | 表达特征线（中纵剖、平底、平边等） |
| `Drawing of the stamp` | 标题栏 stamp |
| `Decks to be drawn` | 要表达的甲板 |
| `Transversal sections of the decks` | 侧视图表达甲板横截面 |
| `Intersection of decks with central plane` | 主视图表达甲板与中纵剖交线 |
| `System of waterlines` | `Default` 9 道水线、间距 T/6；`User system` 自定义 `Increment`/`Waterline` |
| `Additional waterlines` | 额外水线，最多 8 条，按高度输入 |
| `Longitudinal cuts` | 纵剖线半宽值 |
| `Diagonals` | `height`（中心线高度）、`half-breadth`（基线处半宽） |

> 示例目标里的“横剖线、纵剖线、半宽水线”都由 Lines Drawing 输出；界面没有单独“半宽水线”开关，通常由水线系统体现。

### 5.1 自动出图（`foran draw` / `foran fsf build`）

- 已有 `.fsf`：`foran draw --fsf model.fsf --out lines.dxf`。脚本通过 wrapper 启动 FSURF，用 `File > Open` 打开模型，再走 `File > Ship > Drawings > Lines drawing`。
- 从 BREP 壳新建：`foran fsf build --brep shell.brep --fnam TEST --lpp ... --out ... --draw-out ...`，内部依次完成 Import → Manager 分配 patch → Build Ship → Surface Validator → 肋位 → Save → Lines Drawing。
- Lines Drawing 的参数默认：Scale 100、`After - Fore`、水线 9 道（间距 T/6）、`Frames` 标记；`fill_lines_dialog` 只改 Scale/File name，其余保持默认。
- 肋位不定义时 `DsgLinesDrawCmd` 会报 `The Frame system has not been defined`；`fsf build` 用 `File > Ship > Edit frame system` 设 `Nmax=100`、`Spc=Lpp/100`。
- 保存 FSF 必须走 `File > Save` 弹出的 `Save File` 对话框（Ctrl+S 无效），文件名用剪贴板输入；保存后重新打开，肋位保留，DXF 与保存前字节一致。

## 6. 保存与导出

`File > Save` 存当前 `.fsf`；`Save As` 可选：

| 格式 | 内容 |
|---|---|
| `.fsf` | 所有实体（form file） |
| `.nsrf` | Patches |
| `.srfasc` | Patches，ASCII |
| `.cur` | 3D curves |
| `.pol` | 多段线，ASCII |
| `.pnt` | 点集，ASCII |
| `.igs` | Patches + 3D curves（IGES） |
| `.dxf` | 多段线（DXF） |

## 7. 静水力特性（FSURF 内）

命令：`Hydrostatic Characteristics`。

- **必须先有 `FNAMfsurf.fsf`**；没有读取该文件时命令不执行。
- 只算外船壳，**不计甲板/其他表面**。
- 可定义舵/螺旋桨附体，仅用于静水力。
- 输出：设计船宽、设计排水量、Cb、XCB（自船中，向尾为正）、最大横剖面积位置/系数、AP 处面积百分数、Cw、LCW 等。
- 与 FBASIC 的静水力结果可能因附体/板厚设置不同而有差异；示例报告以 FBASIC/设计库为准时要注明来源。

## 8. 常见坑

1. **法向错**：Patch 内外法向反了，静水力/体积全错；检查“里红外绿”。
2. **连接孔**：Patch 间有缝，光顺/计算会出问题；`Holes between patches` 必查。
3. **FNAM 不是 4 位**：Build Ship 不通过，或文件名不符合 FGA/FBASIC 预期。
4. **主尺度没填全**：Lpp、B、T、D 是必填；缺一个 `Build Ship` 不生成。
5. **对称键乱勾**：跨舷 Patch 勾了 symmetric，后续镜像/计算会错。
6. **变换基准选错**：船长变换基准应是 AP（X=0）；船宽基准是中纵剖（Y=0）。
7. **改完没 Build Ship**：FGA 加载的是 `.fsf`，不是当前屏幕；改完要 Build Ship/Save。
8. **直接改 `.fsf` 文本**：二进制/专用格式，不要手改；用 FSURF 打开。
9. **静水力只算外壳**：甲板/舱壁/附体不在内；需要完整浮态用 FBASIC。
10. **Manager 拖放要拖到行文字上**：`Foran Objects Manager` 的 TreeItem UIA 矩形是整行宽，几何中心落在空白处，拖放会被忽略；目标 `External Hull` 取 `rect.left+18`，源 patch 行取 `left+30`。组行（`Surface Entities`）不能拖，必须逐个 patch。
11. **`File > Save` 不是 Ctrl+S**：会弹 `Save File`，File name 为空；中文输入法下 `typewrite` 会把名字改成乱码，必须剪贴板粘贴。目标名已存在还会弹覆盖确认（标题不固定），自动保存用唯一文件名最稳。
12. **`Drawings` 是 QPopup 不是 QTool**：菜单 `File > Ship > Drawings` 展开的是子菜单，不是浮窗；用键盘 `Down×6 → Right → Down×3 → Right → Enter` 进 `Lines drawing`。
13. **Build Ship 后 patch 必须分配到 External Hull**：否则 `Finish` 报 `Ship has not correctly assembled`，FSF 不生成。Manager 右侧 `Work Space > Surface Entities` 的行清空才算完成。

## 9. 命令参考

按功能分组的中文速查：

- 本 skill 的中文速查（原创整理，不含帮助原文）

## 10. 自动化（`foran fsf build`，2026-10-28 更新）

- 菜单全部按 UIA **名称**点击：`File`、`New`、`Export/Import...`、`Import / Merge`、`Ship`、`Edit frame system`、`Save`；旧坐标只作兜底，回退时会打印 `menu ... not exposed`。
- `Import file` 对话框的 `Files of type` 通过旁边的 `Files of type:` 标签找到 ComboBox 再点（不再用固定 `(960,712)`）；文件按 `ListItem` 名称选，`Open` 按按钮名称点。
- `--out` / `--draw-out` 的父目录会自动创建（此前输出到不存在的目录会 `FileNotFoundError`）。
- 实测（`shell_capped.brep`，Lpp=172）：Build Ship + Surface Validator 全页 Checked、frames Nmax=100/1.72 m、FSF 107,194 B、DXF 418,103 B，EXIT=0，无 UIA 回退告警。

### 10.1 退出与保存的健壮性（2026-10-28）

- `cmd_build` 用 `try/finally` 包住启动后的全部流程，失败/异常时也会调用 `close_fsurf()`（实测用坏 BREP 触发失败后无 fsurf.exe 残留）。
- `close_fsurf()` 会轮询 12 s、自动应答 `Please confirm...`（Yes）与 `Information modified`（No），最后用 `WM_CLOSE` 兜底并再轮询 8 s。
- 菜单点击 `_menu_click` 会同时搜索主窗口与 QPopup，且对 popup 项**不抢焦点**（否则会关掉菜单）；设 `FORAN_DEBUG_MENU=1` 可打印每项命中的位置。
- 保存帧系统用的是 **`File > Save as ...`**（会弹 `Save File` 对话框），不是 `Save`（原地保存、不弹框）。

### 10.2 Manager 与 Build Ship（2026-10-28）

- `Structure > Manager` 改为按 UIA 名称点击（`_menu_click`），不再用 `(400,54)/(430,91)`。
- Build Ship 主尺度字段改用 `foran_draw.fill_build_ship()`：按标签找同一行右侧的 Edit，剪贴板粘贴；不再用固定坐标 `(806,215)/(1211,215...)`。
- Manager 拖拽本来就用 UIA 行矩形计算（`_mgr_row_point`），不是绝对坐标；只是行内偏移（+30/+18 px）按文字位置取。
- 回归：`fsf build`（TEST9）EXIT=0，FSF 107,194 B、DXF 418,103 B，与改前一致。

## 11. 示例改造自动化（`foran fsf transform`，2026-10-28）

```bash
$S fsf transform --fsf "/path/to/samplefsurf.fsf" \
  --lpp 175 --breadth 29.8 --fnam SAMPLE --out _foran_work/fsf/SAMPLE_transformed.fsf
```

流程与实测：

1. 复制源 FSF（不动原件），启动 FSURF 并打开副本。
2. `Structure > Decks > Delete decks`：`Select Decks` → `All` → `Delete` → `Done`（实测删除 3 张：PoopDeck/MDeck/FCSDeck）。
3. `Structure > Bulkheads > Delete bulkheads`：本示例模型没有舱壁，`All` 选中 0 个，脚本自动 `Cancel` 跳过。
4. `Edition > Transform > Plane scale`：
   - `Select Parts` → `All` → `Done`；
   - `3D Plane`：X 方向用 `YZ`（X=0），Y 方向用 `XZ`（Y=0）；
   - `Enter float value`：填系数（默认 175/172=1.017442、29.8/28.8=1.034722）。
5. Build Ship 用目标主尺度（`fill_build_ship` 按标签填字段），Surface Validator 全页 Checked。
6. `File > Save as ...` 保存（绝对路径，避免落到 FSURF 的 run 目录）。

实测：FSF 864,164 B（删除甲板后变小）；随后 `foran draw --fsf <transformed>` 出型线 DXF 1,038,690 B。

未自动化（需人工）：尾封板重做、首尾/球鼻艏修型、水线以上外飘、正式型线图标题栏与型值表、Cb/∇/LCB 数值校核（可用 FSURF `File > Ship > Hydrostatic Characteristics` 或团队 `foran_cb_check.py`）。

### 11.1 型值表与静水力校核（2026-10-28）

```bash
# 在 FSURF 里生成 LOFTBOOK（型值表，.lis），并直接用型值表积分
$S fsf offsets --fsf SAMPLE_transformed.fsf --out _foran_work/fsf/SAMPLE_offsets.txt \
  --hydro 9.83,10.27

# 对已有 .lis 离线积分
$S offsets parse --lis _foran_work/fsf/SAMPLE_offsets.lis --draughts 9.83,10.27 --json
```

- `File > Ship > Offset table` 生成 “LOFTBOOK OF HULL FORMS”：第 1 章主尺度、第 3 章按站/水线的半宽（mm）。
- `foran_offsets.py` 解析第 3 章，按梯形法积分：`vol`、`Cb`、`LCB(AP)`、`Cm`、`Cw` 与 ∇。
- 实测精度：示例 `samplefsurf.fsf` → 40,303 m³ / Cb 0.8277 / LCB 90.46（FSURF 值 40,383 / 0.8293 / 90.40，误差约 0.2%，来自 1 mm 取整与站点梯形积分）。
- **发现并解决了一处“假缺陷”**：示例→175/29.8 后，14、15 站的半宽表在 0.05–1.5 m 和 1.5–1.75 m 出现内部 0 段，直接积分只有 ∇@9.83=41,731、Cb=0.8141。逐站检查发现：这些 0 段被非零半宽包夹，且 Surface Validator 仍无自由边——是型值表在 patch 接缝/切点处的采样遗漏，不是真实破洞。
- `foran_offsets.py` 默认用 `repair_internal_gaps()` 对“两端非零、跨度 ≤3 m”的内部 0 段做线性插值，并在 stderr 报出修复的站位；`--no-repair` 可看原始值。
- 修复后（本次练习模型）：T=9.83 → 42,410 m³ / Cb 0.8273 / LCB 92.02；T=10.27 → 44,533 m³ / Cb 0.8315。对照 handoff 目标 42,514 / 0.8293 / 91.98 与 44,644 / 0.8336，偏差约 0.25%，与示例 0.2% 的积分精度一致。
- **自动判定**：`--expect "9.83:42514:0.8293,10.27:44644:0.8336"`（`T:体积[:Cb]`，逗号分隔）会逐行打印 `Δ` 与 `PASS/FAIL`；体积按相对容差、Cb 按绝对容差（`--tol`，默认 0.005）。任一不达标时退出码为 1，可直接用于脚本/CI。

### 5.1 型线图对话框参数（`foran draw --line-*`，2026-10-28）

`Lines Drawing` 对话框的控件全部可枚举，`fill_lines_dialog()` 已改为按 UIA 标签/文字定位：

| 参数 | 对话框控件 | 取值 |
|---|---|---|
| `--scale` | `Scale` 输入框 | 如 `100` |
| `--line-type` | Type of lines drawing | `After-Fore` / `After` / `Fore` / `Two-drawings` |
| `--line-body` | Location of the body | `Centre` / `Right` |
| `--line-marks` | Marks in the axis | `Frames` / `Metres` |
| `--line-diagonals` | Scale for the diagonals | 勾选 |
| `--line-special` | Drawing of special lines | 勾选 |
| `--line-parallel` | Marks for the parallel body | 勾选 |
| `--line-particulars` | Printing of main particulars | 勾选 |
| `--line-stamp` | Drawing of the stamp | 勾选 |
| `--line-deck-sections` | Transversal sections of the decks | 勾选 |
| `--line-deck-centre` | Intersection of the decks with the central plane | 勾选 |

- 都可用 `--no-line-...` 关闭；不传时保持对话框默认值。
- 实测：默认 DXF 1,038,690 B（ARC 2850 / MTEXT 146）；`--no-line-particulars --no-line-stamp` → 1,007,743 B（MTEXT 82，ARC 不变）；`--line-body right --line-marks metres ...` → 503,920 B（半体布置）。
- 标题栏（stamp）由 Build Ship 的 FNAM/描述等船数据生成，默认开启；需要示例模板时以 `--line-stamp` 输出后做 CAD 后处理。

### 5.2 DXF 后处理：图幅 + 边框 + 标题栏（`foran dxf frame`，2026-10-28）

FORAN 的 Lines Drawing 只输出裸几何；`foran dxf frame` 用 ezdxf 把型线放到带图框的图纸上：

```bash
# 保留原图比例，图幅按内容自动放大（本次型线：2145x546 mm）
$S dxf frame --in lines.dxf --out framed.dxf \
  --project "SAMPLE SHIP" --title 型线图 \
  --drawing-no EXAMPLE-010-04 --scale-text 1:100 \
  --designer APPROVER --checker CHECKER --approver APPROVER

# 或缩放到标准 A1（841x594 mm）
$S dxf frame --in lines.dxf --out framed_A1.dxf --fit --sheet A1
```

- `--units-per-mm`（默认 `0.0001`，即 FORAN Lines Drawing 的 1 图形单位 = 0.0001 mm）负责把 DXF 单位换算成 mm；换别的来源时要按实际单位改。
- 自动模式保留原打印比例，只在四周加 25/10 mm 边距和右下 180×56 mm 标题栏；`--fit` 才缩放。
- 标题栏字段：项目、图名、图号、比例、设计/审核/批准、单位、图幅、日期。
- 实测：自动模式 extents 2145×546 mm；`--fit --sheet A1` extents 841×594 mm；TEXT 20 条（中文正常）。
- 依赖 `ezdxf`（已加入 `requirements.txt`）。

### 5.3 合并现成图框（`--template`，2026-10-28）

示例/示例船有专用图框时，先在 CAD 里把图框另存为 DXF，再合并：

```bash
$S dxf frame --in lines.dxf --out framed.dxf \
  --template _work/titleblock_A1.dxf \
  --template-area "25,80,816,580"       # 图框内可放型线的区域（mm）
```

- `--template`：模板 DXF 原样合并（含标题栏文字/图块）；
- `--template-units-per-mm`：模板单位换算（默认 1，即 DXF 单位=mm）；
- `--template-margin`：未给 `--template-area` 时按模板 extents 内缩的边距（默认 10 mm）；
- `--template-area x0,y0,x1,y1`：显式指定型线放置区，避免压住标题栏。
- 实测（合成的 A3 图框）：输出 extents 420×297 mm，模板文字保留，型线 fit scale 0.1848 放入指定区域。

### 5.4 一条命令出带图框的型线图（2026-10-28）

`foran draw` 新增 `--frame-*`，在 Lines Drawing 写完后直接套图框：

```bash
$S draw --fsf SAMPLE_transformed.fsf --out lines.dxf \
  --frame-template _work/titleblock_A1.dxf \
  --frame-out lines_framed.dxf \
  --frame-title 型线图 --frame-drawing-no EXAMPLE-010-04 \
  --frame-project "SAMPLE SHIP" --frame-designer APPROVER
```

- `--frame-out`：同时输出带图框的 DXF；不传则只出裸线图。
- `--frame-template`：现成图框 DXF；不传时自动生成标准图幅+标题栏（可用 `--fit`？在 draw 里固定为自动图幅）。
- `--frame-area`：`auto`（默认，按标题栏位置推断）或 `x0,y0,x1,y1`（mm）。
- 其余 `--frame-project/--frame-title/--frame-drawing-no/--frame-scale-text/--frame-designer/--frame-checker/--frame-approver/--frame-company`。
- 实测：`draw → lines.dxf 1,038,690 B → 自动识别区域 (10,66)-(410,287) → framed 1,017,265 B`，EXIT=0。

### 5.5 DWG → DXF（AutoCAD Core Console，2026-10-28）

如果装有 AutoCAD（2025 或兼容版本）（`<AutoCAD install>\accoreconsole.exe`），可无界面转换：

```bash
$S dxf dwg2dxf --in "SN2542A-010-03_总布置图_2010V.dwg" --out template_full.dxf
# 实测：6,190,468 B DWG → 41,910,538 B DXF，2.8 s，EOF 完整
```

要点（踩过的坑）：

- **Git Bash 会把 `/i`、`/s` 当路径转换**，直接调用会打印 usage 并挂住；命令行加 `MSYS_NO_PATHCONV=1`，或改用 Python 的 `subprocess`（本命令已用后者）。
- 脚本必须 `FILEDIA 0` → `DXFOUT` → 路径 → `16`，然后 **`QUIT` + `Y`**；只按 `QUIT` 或 `N` 会停在“是否放弃修改”而超时。
- 可在 `FORAN_ACCORECONSOLE` 环境变量里覆盖 accoreconsole 路径。
- 转换结果是**整张图纸**（含所有图层）；当图框模板用之前，要在 CAD 里删掉图形内容、只留图框/标题栏（示例图框的标题栏在 `TitleBar` 图层）。
- **重建肋位**：`--rebuild-frames` 在 Build Ship 之后调用 `_define_frame_system`（默认 Nmax=100、间距 Lpp/Nmax；可用 `--frame-nmax/--frame-spacing`），保存的 FSF 已含新肋位。实测 175 m → 1.75 m 间距，FSF 864,176 B。

### 11.3 批量横舱壁（`foran fsf bulkheads`，2026-10-28）

```bash
$S fsf bulkheads --fsf SAMPLE_frames.fsf --x 46.85,60.95,91.38,118.4,146.2 \
  --prefix BHD --start-id 101 --out SAMPLE_bulkheads.fsf
```

- 每道舱壁：`Structure > Bulkheads > New bulkhead` → `Properties` 填 Ident/Name → `Geometry` 选 `X = k` 并填值（m，自 AP）→ `Done` → `Contour` 对话框直接 `Done`（默认按可用限界修剪）。
- `Ident` 从 `--start-id` 递增，名称 `--prefix-01/02…`；`--keep-open` 可留界面检查。
- 完成后用 `Structure > Bulkheads > Delete bulkheads` 的 `All` 计数校验（不删除，只读后 Cancel）。
- 实测：5 道 X=46.85/60.95/91.38/118.4/146.2，计数 5，FSF 889,676 B，EXIT=0。
- 注意：`find_hwnd` 默认是子串匹配，工作目录名含 “bulkheads” 会误匹配主窗口；脚本已改为 `exact=True`。
- 局限：默认限界可满足一般横舱壁；若需要特定轮廓/开口，仍需在 `Contour` 里手工选线。

### 11.4 参数化甲板（`foran fsf decks`，2026-10-28）

```bash
$S fsf decks --fsf SAMPLE_frames.fsf \
  --deck "1:MainDeck:14.8:Main" \
  --deck "9:InnerBottom:2.0:Double-bottom" \
  --out SAMPLE_decks.fsf
```

- `--deck` 可重复，格式 `ID:NAME:HEIGHT[:TYPE[:CAMBER]]`；HEIGHT 为基线以上高度（m）。
- `TYPE` 可选：`Normal / Main / Forecastle / Bridge / Poop-deck / Double-bottom / Upper-Tanks`；缺省按 ID（1=Main、9=Double-bottom、11=Forecastle、12=Bridge、13=Poop-deck）。
- 流程：`Structure > Decks > New deck` → 选 Type → 填 Identifier/Name/Base height → 勾 `Parametric deck` → `Limit with = External Hull` → `Type of camber = Plane`（默认）→ `Done`。
- 完成后 `Delete decks > All` 计数校验（Cancel 不删），再保存。
- 实测：主甲板 @14.8 + 内底 @2.0（Double-bottom），计数 2，FSF 864,176 → 2,357,646 B，EXIT=0。
- 局限：默认 Plane 拱度、无折点/舷弧；特殊拱度、折点、抛物线舷弧需在对话框里另填。

### 11.5 双壳内壳预设（`foran fsf inner-shell`，2026-10-28）

```bash
$S fsf inner-shell --fsf SAMPLE_frames.fsf \
  --main-deck-z 14.8 --bottom-z 2.0 --side-y 12.5 \
  --x 46.85,60.95 --out SAMPLE_inner_shell.fsf
```

- 一次会话内依次建：主甲板（`--main-deck-z`，可省）→ 内底（`Double-bottom`，`--bottom-z`，默认 2.0）→ 可选横舱壁（`--x`，`X=k`）→ 双舷内壁（`Y=--side-y`，`symmetrical`，默认 12.5 m）。
- 完成后分别用 `Delete decks` / `Delete bulkheads` 的 `All` 计数校验，再保存。
- 实测：主甲板 14.8 + 内底 2.0 + 2 道横舱壁 + 1 道对称内壁 → decks 2 / bulkheads 4，FSF 2,373,090 B，EXIT=0。
- 局限：内壁是平面 `Y=±k`，**没有 hopper/knuckle 折角**；内底与内壁的交线、首尾修剪、开口仍需人工修整。

### 11.6 一条命令跑完 AUTHOR 链路（`foran fsf workflow`，2026-10-28）

```bash
$S fsf workflow --fsf samplefsurf.fsf --lpp 175 --breadth 29.8 --fnam SAMPLE \
  --main-deck-z 14.8 --bottom-z 2.0 --side-y 12.5 --x 46.85,60.95 \
  --rebuild-frames --expect "9.83:42514:0.8293,10.27:44644:0.8336" \
  --draw-out lines.dxf --frame-template template_A3.dxf --frame-out framed.dxf \
  --out SAMPLE_workflow.fsf
```

- 顺序：删旧结构 → Plane Scale X/Y → Build Ship/Validator → 肋位 → 主甲板/内底/横舱壁/对称内壁 → 保存 → Offset table 积分+expect → Lines Drawing → 套图框。
- 实测：静水力 42,423/0.8276/92.01 与 44,552/0.8318，偏差 0.21% PASS；FSF 2,373,092 B；lines DXF 1,057,973 B；framed DXF 1,041,085 B；EXIT=0。
- `--no-inner` 可只做变换+校核+出图；`--keep-decks/--keep-bulkheads` 保留原结构。
- 耗时（2026-10-28 实测，示例→175/29.8 + 内壳 + 出图）：总计约 313 s。分布：启动+删结构 20 s、Plane Scale 41 s、Build Ship+Validator 87 s、肋位 10 s、内壳 112 s、保存 6 s、型值表 17 s、出图 20 s。命令始终打印 `timing : <phase> <s>`。剩余时间主要是 FORAN 自身重算；只改内壳时用 `inner-shell --replace`（约 2 分钟）比重跑整条 workflow 快得多。

### 11.7 Hopper / knuckle 折角内底（`foran fsf hopper`，2026-10-28）

```bash
$S fsf hopper --fsf SAMPLE_frames.fsf --z 2.0 --flat 11.0 --slope 3,1.5 \
  --trace 60:0:9.0 --out SAMPLE_hopper.fsf
# 或并入内壳/整条链路：
$S fsf inner-shell ... --hopper 3,1.5 --flat-halfbreadth 11
$S fsf workflow ... --hopper 3,1.5 --flat-halfbreadth 11
# 双折角（Trapezoidal with two knuckles）：
$S fsf hopper ... --flat 7 --slope 3,1.0 --flat2 11 --slope2 2,0.8
$S fsf inner-shell ... --hopper 3,1.0 --flat-halfbreadth 7 \
  --hopper2 2,0.8 --flat-halfbreadth2 11
```

- 原理：内底用甲板 `Type of deck = Double-bottom` + `Type of camber = Trapezoidal`。对话框给出：
  - `L`：斜板水平投影长度（m）；`H`：斜板抬升高度（m）——两者共同定义 hopper 角；
  - `Traces` 表：每个折点的 `Frame / Dist. to frame / X / Z relative / L`，其中 `X`、`Z relative`、`L`（平底半宽）可编辑。
- 站点编辑：Qt 表格单元格**必须 `F2` 进入编辑**，再用剪贴板粘贴并 `Enter`；双击会清空单元格为 0。两端站默认位于船体限界，`--flat` 只改其半宽，`--trace X:Z:L` 只追加中间折点。
- 校验：设置后立即回读 `L/H` 控件与 Traces 单元格数值（容差 1e-3）；不一致即失败。实测单折点（X=60、L=9）与两端 L=11 均读回一致。
- 实测：`fsf hopper` → decks 1（was 0），FSF 2,463,936 B；`inner-shell --hopper` → decks 2 / bulkheads 4，2,893,145 B；`workflow --hopper` → 静水力 42,423.4/0.8276 与 44,551.6/0.8318，PASS，FSF 2,893,147 B，lines DXF 1,057,973 B，EXIT=0。
- camber 下拉共有 9 项：`Plane / Platform / Trapezoidal / Trapezoidal with two knucles / Variable in angle / Plane-Parabolic / Parabolic-Plane / Circular-Plane / Constant angle`。`Upper-Tanks` 是**甲板类型**而非 camber，其对话框没有 camber 下拉。
- 沿船长变平底：`inner-shell/workflow --hopper-trace X:Z:L[:L2]`（可重复，按 X 排序）；`hopper` 命令对应 `--trace`。实测 `--hopper-trace 60:0:9` → decks 3 / bulkheads 4、FSF 3,813,060 B。
- 单元格写入：每次 `F2` 编辑后立即回读校验，不一致会自动重试一次；仍不一致才失败。
- 重复迭代：`hopper --replace` / `upper-tank --replace` 先用 `Delete decks` 的选择对话框删掉同名/同 id 的旧甲板（其它甲板保留），再建新的；`inner-shell --replace` 还会按 `BHD-`/`INNER-01` 前缀清掉上次建的舱壁。选择对话框的用法：`All` 入列 → 高亮要保留的行 → 点右侧 `Delete` 移出工作列表 → `Done` 删除剩余行。
- 双折角：`--slope2 L2,H2 --flat2 <半宽>` 选用 `Trapezoidal with two knucles`（UI 拼写如此），Traces 表多一列 `L2`，`--trace` 可写 `X:Z:L:L2`。实测 decks 1、FSF 2,631,445 B；`inner-shell --hopper2` → decks 2 / bulkheads 4、FSF 3,084,291 B，均 EXIT=0。
- 局限：`File > Export/Import... > Export to decks and bulkheads` 只导出平面/无折点甲板，梯形 camber 甲板不会写进 XML（`DeckGroup` 为空），故不能靠 XML 校核；Upper-Tanks（camber 参数 H/L/ALPHA）尚未参数化。

### 11.8 Upper-Tanks 甲板（topside tank，`foran fsf upper-tank`，2026-10-28）

```bash
$S fsf upper-tank --fsf SAMPLE_inner.fsf --l 8 --h 3.3 --alpha 45 \
  --out SAMPLE_upper_tank.fsf
# 并入内壳/整条链路（必须先有主甲板）：
$S fsf inner-shell ... --main-deck-z 14.8 --upper-tank 8,3.3,45
$S fsf workflow ... --main-deck-z 14.8 --upper-tank 8,3.3,45
```

- 对话框固定项：`Type of deck = Upper-Tanks` 后，`Base height` 灰显为 `Main deck`、`Limit with` 灰显为 `External Hull 0`、`Type of camber` 灰显为 `Upper tanks`，**都不能改**；`Add/Delete/Clear` 三个 Traces 按钮禁用，只有两端站可改。
- 可编辑参数：`L`（垂向内壁半宽）、`H`（内壁高出主甲板的高度）、`Alpha`（hopper 角，度）；Traces 表列是 `Frame / Dist. to frame / X / L`（无 Z 列），两端 L 设为 `--l`。
- **必须先有主甲板**：模型没有 Main deck 时，三个字段输入后会被立即重置为默认值（L=8、H=1、Alpha=45），预览显示 `not available`；回读校验会报 `camber H read back as 1.0`。命令已在该情形给出提示。
- 重复迭代用 `upper-tank --replace`（先删同名/同 id 的旧 UpperTank）。
- 实测：在示例变换 + 主甲板 14.8 + hopper 内底 2.0 的模型上，`upper-tank --l 8 --h 3.3 --alpha 45` → decks 3（was 2）、FSF 3,757,418 B、EXIT=0；`inner-shell --upper-tank` → decks 3 / bulkheads 4、3,757,413 B；`workflow --upper-tank` → 静水力 PASS、FSF 3,757,416 B、EXIT=0。
- 局限：Upper-Tanks 不能沿船长加折点（Add 禁用）；`Upper tanks with flat bottom` camber 尚未参数化。

### 11.9 型线交付包（`foran deliver lines`，2026-10-28）

```bash
$S deliver lines --date 20261109 --version v0.1
```

- 在 `fsf workflow` 之外补齐：清 FORAN 原图框/比例戳 → A0 套框（比例按实际轮廓反算）
  → 图上画 17×21 型值表和面积曲线 → DWG → 静水力校核表 → README/SHA256/ZIP。
- `workflow` 新增 `--draw-scale`（默认 100）；交付包默认 300，使套框后字高约 2.3–5.7 mm。
- **Offset table 对话框不能写中文路径**：`deliver` 把所有 FSURF 工作放在
  `_foran_work/deliver/_run_<stamp>/`（ASCII），最后复制进中文包名。
- 详见 。
