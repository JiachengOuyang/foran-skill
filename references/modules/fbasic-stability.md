# FBASIC — Stability Tree 与概率破舱

> 按实际操作整理。软件 V80R3.0；不同版本的字段可能略有差异。

## 1. Stability Tree 结构

```text
Stability Criteria     稳性规范（内置/自定义）
Formulation            计算表达式
Loading Condition      工况（完整稳性校核）
Groups of Loads        装载组（可复用配载）
Initial situations     破损前初始状态
Damages                破损位置（手动/自动）
Flooding               确定法破舱校核
Max KG calculation     极限重心高/极限 GM
```

## 2. Stability Criteria（稳性规范）

### 2.1 调用内置规范

右键 `Stability criteria > Add SSCs`，从内置列表选择规范并初始化。

常见初始化参数：

- `IS2008-Passenger`：`Number of passenger`、`Passenger heeling lever arm`、`Weight per passenger`；`Heel due to turning` 的 `Service speed`。
- `IS2008-Weather`：`Bilge keels area`、`Deck immersion`、`Domestic voyages`、`Fishing vessel 24<L<45m`、`Wind pressure`（默认 504 Pa；渔船为 0 时按规范算）、`k factor`、`φr roll angle`（0=系统算）。

### 2.2 自定义规范（USC）

1. 右键 `Stability criteria > New node`，建规范目录（如 `USC1`）。
2. 右键目录 `New criteria`，建衡准（如 `USC-XL`）。
3. 右键衡准 `Edit`，添加条款：
   - `Entity`：`GM` 初稳性高、`Heel` 横倾角、`GZ` 回复力臂、`DNS` 动稳性、`Distance` 距限界线距离。
   - `Property`：关联对象的具体属性。
   - 点图标，按示意图输入参数。
4. `Export USCs` / `Import USCs` 导出/导入 XML，跨项目复用。

## 3. Formulation（计算表达式）

用于自定义规范里的复杂衡准。

1. 右键 `Formulation > New Formula`。
2. `Name`、`Description`、`Definition`（表达式）。
3. `Function`：双击插入函数。
4. `Parameters`：双击插入参数；可新建参数（name/description/value/unit）。
5. `User tables`：新建表格，输入 X/Y 值。
6. 示例：`interpolate("Table_1", VAR_HEELANGLE)`。
7. 应用到衡准：右键 `USC-XL > Edit`，用表达式增加横倾角条款。

## 4. Loading Condition（工况）

### 4.1 基本信息

右键 `Loading Condition > New Loading Condition`：

- `Name`、`Description`；
- `Lightship Weight`：选空船重量样式；
- `Opening`：进水点样式；
- `Wind profile`：受风轮廓；
- `Wave profile`：波浪样式（可选）；
- `Middle draught calc.`：散货船按目标平均吃水反算货物密度；
- `Group of loads`：装载组（可选，组改则工况自动更新）；
- `Stability`：要校核的规范；不选=所有激活规范。

底部图标：保存退出 / 保存并新建 / 保存并复制 / 取消 / 预览。

### 4.2 配载

**Loads in compartments**（液体/散货）：

- 从 `Spaces` 拖液体舱到列表；或用搜索：勾 `Load types` → 选介质（fuel oil/diesel oil 等）→ 列出舱室 → 拖入。
- 列：`Filling%`、`Weight`、`FS Corr`（自由液面修正方法）、`FS heel`（液货舱自由液面横倾角）、`FS fill%`（液货舱自由液面装载率）、`GZ corr`（回复力臂修正）、`UD`（按目标平均吃水反算密度，散货船）。
- 点列标题排序；拖列标题改顺序。

**local loads**（人员/备品/货物等非液体）：

- `Name`（不重复）、`Weight`、`Aft limit`/`Fore limit`（可写 `fr35+200`）、`XCG/YCG/ZCG`、`Cargo type`（默认 user）。

**Modular loads**（模块化货物）：

- `Group` 选已定义箱组；或底部按钮选箱组排布；可单独改某箱重量。

### 4.3 预览与计算

1. `Update` 显示配载结果：排水量、吃水、重心、GM 等。
2. 三向预览：主视图底部点选 → 侧视图横剖；左右端点选 → 俯视图水平剖；中键重置。
3. 选项卡：`Stability curves` 稳性曲线、`Stab Table` 稳性表、`Stab criteria` 条款校核（全绿=满足）、`LS-curve` 总纵强度。
4. 底部切换：稳性计算 / 总纵强度 / 规范校核。
5. 右键工况 `Run` 计算；`Report` 出报告；`Summary` 出工况汇总。
6. 工况名旁图标：已算/未算。

## 5. Group of loads（装载组）

- 右键 `Groups of Load > New Group Loading`。
- `Name`、`Description`；用 `loads compartments` / `local loads` / `modular loads` 配载（同 4.2）。
- 在工况里通过 `Group of loads` 加载；组内配载灰色显示，手动添加白色。
- **改组会影响所有引用它的工况**。

## 6. Initial situations（初始状态）

用于定义破损前状态。

- 右键 `Initiate situations > New Initial`。
- 手动：`Identification/Description`、`Aft draft`/`Fore draft`、`Height of COG`、`Opening`、`Wind profile`、`Margin line`。
- 从工况加载：勾选工况 → 按钮添加到列表 → 可再编辑。

## 7. Damages（破损位置）

### 7.1 手动

右键 `Damages > New Damages`：

- `Name/Description`；`Water on deck calculation`（滚装船甲板积水）。
- 三向视图选破损舱室：左键拉框选中、右键拉框取消；也可用图标从对话框增删。
- 每舱：`Permeability`、`Initial filling`、`Initial density`、`initial stage`、`Total stage`（中间进水）。

### 7.2 自动生成

右键节点 `Generate Damages`：

- 底部破损 / 舷侧破损；左舷/右舷；
- 命名方式：`General`（手输范围）/ `MARPOL`（按公约破损范围）；
- 输入长度、跨度、高度方向破损长度；
- 生成后逐条检查，别直接用于计算。

## 8. Flooding（确定法破舱）

1. 右键 `Floodings > New Flooding`。
2. 选初始状态（可多选）、破损位置（可多选）；系统自动组合。
3. 右键破损组合 `Calculates`，按当前激活的破舱稳性规范算。
4. `View` 预览；`Report` 出报告。
5. 图标：已算/未算。

## 9. Max KG calculation（极限重心高）

1. 右键 `Max KG calculation > New Calculation`。
2. `Type of KGMAX calculation`：`INTACT`（完整）/`DAMAGE`（破损）。
3. `Draughts table`：`Min mean draught`、`Max mean draught`、`Number of draughts`、`Trim`（尾倾正）、`Initial KG`。
4. `Loading condition`：选工况。
5. `Damage` 类型才需要：`Initial situation`、`Damages`（图标选）。
6. `Opening`、`Wind profile`、`Stability`（破舱规范）。
7. `Calculate` → `Report`；右键 `KG Maximum diagram` 看曲线，可切 `KG`/`GM`。

## 10. 概率破舱（Probabilistic damage stability）

### 10.1 Section Definition（限界面）

`Entities > Sections > Edit Sections`，三种选项卡，每种可建多个方案（结果可能不同）：

- `Transversal`：横向限界面。左栏 `+` 新建样式；中间栏 `+` 加位置；用 `abcissa`（绝对坐标）、`Frame`（肋位+偏移）、`Bulkhead`（选横舱壁）。
- `Longitudinal`：纵向限界面。`Main` 用 `Halfbreadth`（距中）或选纵舱壁；`AFT/Fore limit` 用 `abcissa`/`Frame`/`Bulkhead`。
- `Horizontal`：垂向限界面。`Main` 用 `height` 或选甲板；`AFT/Fore limit` 同上。

### 10.2 Initial Situations

同第 6 节；概率破舱通常要按规范取 `Deep`/`Light`/`Part` 三种吃水。

### 10.3 General Options

右键 `Probabilistic Calculation > Edit general options`：

- `Type of calculation`：`Initial`（FGA 还没建具体舱室，前期设计）/`Final`（FGA 已建舱室，精确）。
- `Openings Group`：校核开孔。
- `Passenger ship`：乘客数（`N1` 有救生艇、`N2` 无救生艇、`N` 总数）、乘客倾覆力矩（可手输）、救生艇重量/力臂。

### 10.4 Select Regulation

右键 `Probabilistic Calculation > New regulation`，选规范（如 SOLAS）。

### 10.5 Subdivision Cases（破损组合）

右键规范节点 `New Subdivision`。

**Definition 选项卡**：

- `Subdivision Statues`：`Identification/Description`、`Definition`（`Validate` 后 OK/Not OK）、`Spaces/Subzones`（Associated/Not associated）、`Processed`。
- `Obtain subdivision values`：自动取分舱甲板前/后端，算分舱长度与要求指数 `R`；可改长度。
- `Geometric subdivision`：选限界面样式（横向必选，纵向/垂向可选）。
- `Initial Situations`：选 `Deep`/`Light`/`Part`。
- `Grouping level`：最大破舱数（如 3=最多三舱破）。
- `Validate`：通过后其他选项卡才激活。

**Compartments（单舱）**：按横向限界面分成大舱，命名 `C[aft][fore]`（如 C012028）；纵向限界面给 `b` 值，垂向给 `h` 值；可编辑，`Recalculate all b's/h's` 重算。

**Groups（舱组）**：`GA[aft][fore]`（两大舱）、`GB...`（三大舱）；b/h 同上。

**Subzones（子区域）**：由纵/横/垂限界面+外壳分割，命名 `Z[aft][fore]W[i]H[j]`（W 从船壳 0 向内，H 从基线 0 向上）。`Associate spaces` 自动关联舱室；`Recover association` 重关联（丢手改）；`Details` 或右键 `Edit subzone` 可动选/取消舱室、设中间进水阶段。

**Spaces（渗透率）**：默认取 FGA 装载类型；可改；`Special` 可自由输入各水线渗透率。

**Damaged zone（破损区域）**：查看当前组合所有破损形式；三种装载吃水；`Hull`/`Hull+Bulk`/`Hull+Deck+Bulk` 等；每个形式取最小 `Si`；`Save as` 导出 txt/xls。改过 b/h 后要重算破损形式。

**Copy of Subdivision**：右键 `Copy`，可改名字、放到别的规范下、复制初始状态/限界面。

### 10.6 Reg.7/8 校核

- 右键 `Reg 7 > Calculate`，勾装载/破损区域，`Calculate`；达到的指数 `A` 与要求 `R` 比较。
- `Create reports`：`Summary` 或 `Complete`（可含 general data、openings、破损形式、概率因子、参考点、浮态/稳性、中间进水）。
- `Create drawings`：输出破损位置草图，可 `Create a single document`。
- `Reg 8 > Create report`：Reg.8 报告。

### 10.7 Reg.9 校核

- `Reg 9 > Damages`：`New Damages` 手动或 `Generate Damages` 自动（纵/横/垂范围按规范，命名 `DC-001`）。
- 右键破损位置：`Edit`/`Create drawings`/`Delete`/`Copy`。
- `Floodings > New flooding`：选初始状态+破损位置，系统组合；`Calculate`。
- 右键破损形式：`Edit`/`Deleted`/`Calculate`/`View`。
- `Reg 9 > Create report`，选择破损形式，生成报告预览。

## 11. Other（其它）

| 命令 | 作用 |
|---|---|
| `Custom > Generate Margin Line Immersion angles tables` | 限界线在不同水线/吃水差下的入水角表；输入最小/最大吃水、步长、最小/最大纵倾、步长、是否自由纵倾（需 KG）、限界线 |
| `Custom > Generate Opening Immersion Angles Tables` | 进水点入水角表；同上，选进水点类型 |
| `Custom > Generate Trimming Tables` | 吃水差变化表；输入吃水/纵倾范围、步长、舱内重量、初始 KG |
| `Report customization` | 自定义报告模板/输出 |

## 12. 常见坑

1. **规范没初始化**：`Add SSCs` 后要 `Edit` 填参数（风压、乘客、舷龙骨等）。
2. **工况没选规范**：不选=校核所有激活规范；想只校核某规范要显式选。
3. **装载组改动**：会影响所有引用它的工况，改前确认。
4. **破损位置自动生成**：`Generate Damages` 后必须逐条检查，尤其 `MARPOL` 范围。
5. **b/h 手改后**：必须重算破损形式，否则 Reg.7/8 结果旧。
6. **概率破舱 Initial vs Final**：FGA 没建舱室只能用 `Initial`；有舱室要用 `Final`。
7. **Subdivision 未 Validate**：其他选项卡不激活。
8. **单位/吃水基准**：初始状态吃水、纵倾正负（尾倾正）要统一。
9. **Reg.9 与 Reg.7/8 是两套**：Reg.9 有自己的 Damages/Floodings 树。
