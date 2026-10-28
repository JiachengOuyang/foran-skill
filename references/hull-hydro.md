# 参数化船体与静水力（无 GUI）

> 2026-10-26 实测。对应命令：`foran hull gen`、`foran hydro calc/compare`。
> 不启动 FORAN，纯 Python；生成的 BREP 可再交给 FGA/FSURF。

## 1. 参数化船体（`foran hull gen`）

船体由站截面生成：

```text
u = x / Lpp
y(x,z) = A · (B/2) · f(u) · g(v),   v = z / T
```

- `f(u)`：纵向丰满度。平行中体 `[0.2, 0.8]` 内为 1，两端按 `sin(π/2·...)^q` 收尖（艉 q=0.6，艏 q=1.2）。
- `g(v)=sin(π/2·v)^p`：垂向截面形状；`p` 越小越丰满（p→0 近似矩形截面）。
- `A`：整体放大系数；只有目标 Cb 超出 `p` 可调范围时才用。
- 截面多边形：`(0,0)` → 左舷甲板 → 甲板 → 右舷甲板 → `(0,0)`，闭合。

### Cb 校准

`Cb` 随 `p` 单调下降。命令在 `p∈[0.002,3]` 内二分 50 次命中 `--cb`；若目标高于 `p=0.002` 的 Cb，则 `A=target/Cb` 并报告实际船宽放大。实测 172/28.8/9.83/14.6、Cb=0.83 → `p=0.0185, A=1.0`。

### 输出

| 文件 | 内容 |
|---|---|
| `sections.json` | 站号、x、截面点 (y,z) |
| `lines.svg` | 横剖（body plan）、纵剖、4 条水线 |
| `hydro.json` | 参数、校准结果、设计吃水静水力 |
| `report.md` | 可读报告 |
| `hull.brep` / `hull.step` | `--brep` / `--step`，gmsh OCC 闭合实体 |

### 实体与积分的一致性

20 站 × 20 层截面的 172 m 船体：

```text
设计吃水 T=9.83：volume = 40,415.927 m³  (Cb=0.8300)
到甲板 D=14.6：  volume = 60,752.809 m³
gmsh BREP 体积：  60,752.809 m³   (完全一致)
```

## 2. 静水力（`foran hydro calc`）

### 数据来源

`DSG_SOLID_HULL_SECTIONS`：

```text
OID, ENT_TREE_OID, NE, X, DATA
DATA = 12-byte header + N × 5 × float32(big-endian)
       header = >III(?, 0, counter)
       每个点前两个 float 是 (Y, Z)，后三个是哨兵值
```

`foran_hydro.load_sections()` 按 X 排序读取；截面多边形闭合。

### 计算

对每个站，把截面多边形用 Sutherland–Hodgman 裁到 `Z ≤ T`，得到：

- 面积 `A(x)`、对 Z=0 的一阶矩 `Mz(x)`、水线处 `y_min/y_max`、湿周长。
- 沿 X 梯形积分：

```text
∇  = ∫ A dx
LCB = ∫ A·x dx / ∇
KB  = ∫ Mz dx / ∇
Awp = ∫ (y_max-y_min) dx
LCF = ∫ w·x dx / Awp
IT  = ∫ w³/12 dx
IL  = ∫ w·(x-LCF)² dx
BM_T = IT/∇,  KM_T = KB+BM_T
TPC = ρ·Awp/100
MCT = ρ·IL/(100·Lpp)
Cb = ∇/(Lpp·B·T), Cp = ∇/(Am·Lpp), Cm = Am/(B·T), Cwp = Awp/(Lwl·Bwl)
```

### 与 FBASIC 的对比（sample，T=9.83）

| 项 | 本工具 | FBASIC | 差 |
|---|---|---|---|
| Volume (m³) | 40,373.57 | 40,383.13 | -0.024% |
| Displacement (t) | 41,382.91 | 41,392.71 | -0.024% |
| Cb | 0.82913 | 0.82933 | -0.024% |
| Cp | 0.83279 | 0.83299 | -0.024% |
| Cm | 0.99560 | 0.99561 | ~0 |
| LCB (m) | 90.417 | 90.403 | +0.014 m |
| LCF (m) | 84.232 | 84.271 | -0.039 m |
| KB (m) | 5.1474 | 5.1469 | +0.0005 m |
| BM_T (m) | 7.1915 | 7.1892 | +0.0022 m |
| KM_T (m) | 12.3388 | 12.3361 | +0.0027 m |
| TPC (t/cm) | 47.032 | 47.083 | -0.05 |
| MCT (t·m/cm) | 594.05 | 596.27 | -0.37% |
| Wetted (m²) | 7,575.06 | 7,416.94 | +2.4% |

- Wetted 偏高是因为按截面湿周长积分，可能把甲板/内部边也算进去；其余全部在 0.1% 内。
- 只支持 **正浮（even keel）**；纵倾/横倾水线尚未实现。
- 截面数据来自 `DSG_SOLID_HULL_SECTIONS`；只适用于已经 Build Ship/有 hull solid 的项目。

## 3. 与 FORAN 的衔接

- `hull.brep`/`hull.step` 可用 `foran fga brep --brep ... --node CARGO` 导入 FGA，作为一个闭合 space（实测 volume=60,752.809、bbox x0..172/y±14.4/z0..14.6）。
- **FSURF 导入已试通一半**：`File > Import > Import/Merge` 的文件类型支持 `*.fsf`、`*.dkbh`、`*.nsrf`、`*.srf`、`*.srfa...`、**`*.igs`**、**`*.stp`**、**`*.brep`**、`*.cur`、`*.pol`。用 IGES 和 BREP 都能把生成的船体读进 FSURF 场景。
- **第一次导入（实体）**：Work Space 里有 **862 个 patch**；Manager 里把 `Surface Entities` 组直接拖到 `External Hull` 会报 `Can't add this kind of object.`，只能逐个 patch 拖（862 个不现实）。
- **第二次导入（低 patch 壳）**：用 `nz=4` 的粗截面 + `makeSolid=False, makeRuled=False` 生成 **11 个 patch** 的 `hull_shell.brep`；FSURF 能打开，Build Ship 也能填字段并通过 Surface Validator（Duplicated/Lines 用 `Analyze all surfaces`），但点 `Finish` 后报 **`Ship has not correctly assembled`**。原因是这些 patch 还在 Work Space，没有分配到 External Hull。
- **Manager 仍是卡点**：11 个 patch 的 `Surface Entities` 在 Manager 右上只显示为一个类别行，展开不出具体 patch；组拖被拒。需要找到批量分配入口（或逐个 patch 的列表），才能完成 Build Ship。
- 下一步：
  1. 找到 Manager 的 patch 列表/批量分配方式（或 SENER 手册里的 Manager 批量操作）；
  2. 或者用 FSF/数据库层面支持的其它方式设置 hull membership；
  3. 打通后 Build Ship → 保存 `.fsf` → FGA/FBASIC。
- `foran hydro calc` 只读 DB，不写库；`compare` 会逐站对比 FBASIC 的 `DSG_HYD_RESULTS`。
