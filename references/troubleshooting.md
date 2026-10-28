# FORAN 故障排查

先跑：

```bash
foran env check
foran journal summary --latest
```

## 快速对照表

| 现象 | 最可能原因 | 处理 |
|---|---|---|
| 双击 exe 闪退 / 无窗口 | 直接运行 exe，缺 `FORAN_HOME`/`TCL_LIBRARY` 等 | 走包装 bat 或 `foran launch <module>` |
| 进程在但主窗口不出现；日志/弹窗 `WinSock: Connection refused` | `LM_LICENSE_FILE` 指向失效的 `port@...`（MSC） | 用包装脚本；确认 `foran env check` 的 license 路径；**不要改全局变量** |
| 启动时 `Journal folder does NOT exist: X:/ForanLogs` | 官方 `installation.txt` 写死旧部署路径 | 包装脚本的 `FORAN_CONF` 指向本地 conf |
| `fbasic`/`fga` 弹 `Database settings` | 这两个模块必须有项目库 | `Open DB file` 选 `.db`；不要选 `Create a new database`（空库没数据） |
| `Invalid database file.` | 不是 FORAN 项目库 / 传输损坏 / 选错文件 | 确认是项目提供的 `<FNAM>.db`；重新拷贝；仍报错联系提供方 |
| `Database X is locked` | 库在只读/U 盘位置，或另一进程占用 | 复制到本地可写目录再开；关闭其他打开该库的模块 |
| `Database from an older FORAN version...` | 库版本旧 | 允许更新（先备份）；若库比 V80R3.0 新，需要更高版本 FORAN |
| `Database %1 not found.` | 路径写错或文件被移走 | 用绝对路径；先 `foran db check` |
| `fsurf` 标题没有 许可信息 | 许可没读到 | 检查 `LM_LICENSE_FILE` 是否是 FORAN 的 `.lic`；用包装脚本 |
| 库打开后查询不到数据 | 打开的是空库/错库 | `foran db check` + `foran db tables --filter ...` |
| 宏菜单里看不到新宏 | 菜单没刷新 / 文件不在工作目录 | `Tools > Macros > Refresh menu`；确认工作目录（快捷方式 Start in） |
| GUI 自动化 `controls` 看不到控件 | Qt 窗口对 UIA 暴露不完整 | 换 `--backend win32`；或退回截图 + 坐标点击 |
| 截图全黑 | OpenGL/硬件加速窗口抓不到 | 先尝试全屏截图；再用 `Print Screen` 对比；必要时关硬件加速 |
| `UIA` 报权限错误 | FORAN 以管理员运行，脚本没有 | 用同样权限运行脚本；或改为手工操作 |

## 1. 许可（最常见）

证据链：

```text
全局 LM_LICENSE_FILE = port@license-server   → 本机该端口无服务
FORAN 读同一个 FlexNet 变量 → Connection refused → 启动中止
```

- 只对 FORAN 进程设置 `LM_LICENSE_FILE=<FORAN_INSTALL>\foran_licensing\<your.lic>`。
- 不要试图把 `.lic;port@...` 写在一起：实测仍失败。
- 不要改全局变量：MSC/Patran 还在用。
- `foran_launch.py` 已在子进程 env 里设置，不依赖用户手工操作。

## 2. 项目库

- FORAN 项目库是 SQLite；`FORAN_VERSION` 表可读出版本，例如 `V80R3.0.012-2`。
- 打开前先复制：

```bash
foran db copy "C:/FORAN/projects/sample.db" --out-dir ".\_foran_work\projects"
```

- 只读检查：

```bash
foran db check "C:/FORAN/projects/sample.db"
foran db hydro "C:/FORAN/projects/sample.db"
```

- 项目提供的库如果版本旧，用 `...\bin\update_db.bat`（会套用 `run\proyecto\dsgfil\sqlite_patches\`），或在 GUI 里允许更新。更新前必须备份。

## 3. 日志

位置：

- `C:/FORAN\logs\*.jrnl.csv`
- `%USERPROFILE%\.foran\journal\*.jrnl.csv`

看最新一次：

```bash
foran journal list
foran journal summary --latest
foran journal errors --latest
```

典型错误：

| 日志内容 | 含义 |
|---|---|
| `DLGMESSAGE message=Invalid database file.` | 选错库/库损坏 |
| `DLGMESSAGE message=Database ... is locked` | 库被占用或只读 |
| `WinSock: Connection refused` | 许可服务器连不上（通常是 MSC 变量） |
| `Journal folder does NOT exist` | `FORAN_CONF` 没生效 |
| `HOLTROP Method only valid for angle value between 0 deg to 90 deg` | 某次计算参数超范围；不代表启动失败 |

## 4. 启动器参数陷阱

- `fdm.bat`、`fsurf.bat` 没有 `-sqlite`；不要给它们传数据库。
- `fbasic.bat`、`fga.bat` 带 `-sqlite`；库通过 `Database settings` 选，**不要假设 `-fnam` 一定可用**。
- 启动器的 `--extra` 会把参数转发给 bat；不确定的参数先 `--dry-run` 看命令。
- 工作目录影响宏和相对路径文件；默认 `.`（快捷方式的 Start in）。

## 5. GUI 自动化失败

1. 先 `foran gui windows --filter foran` 确认窗口标题。
2. `foran gui controls --window "<标题>" --backend uia --dump out.txt`。
3. 如果控件树只有一层：换 `--backend win32`。
4. 仍不行：用 `foran gui screenshot --window "<标题>"` + `click --pos x,y`（屏幕坐标），每次操作前后截图核对。
5. FORAN 若以管理员启动，脚本也必须同权限，否则 UIA 连接失败。

### 实测：FDM 的 Qt 窗口只暴露标题栏

2026-10-26 实测 `FORAN Document Manager`（class `QWidget`，pid 为 `fdm.exe`）：

- `windows` 能正确枚举；
- `screenshot --window` 能拿到完整窗口（922×856）；
- `controls --backend uia` 只看到 `MenuBar(系统)` 和最小化/最大化/关闭按钮，**菜单 File/Find/View/Document/Help 和工具条都看不到**；
- `controls --backend win32` 只看到顶层 `QWidget`。

### 窗口标题乱码（pywinauto UIA）

实测 `pywinauto.Desktop(backend="uia").windows()` 会把部分 Qt 窗口标题解码成乱码（`Lines Drawing` → `������`），导致找不到窗口。**窗口枚举/查找请用 `foran_gui.windows()`（win32gui）**，找到 hwnd 后再用 pywinauto 连控件。`foran_draw.py` 已经这样做。

因此对 FORAN 的 Qt 窗口：

- 能用键盘快捷键就用快捷键（`foran gui keys --keys "alt+f"`、`ctrl+o` 等）；
- 需要点菜单/工具条时，用截图 + `click --pos x,y`（屏幕坐标）；
- 不要指望 `click --name "Open"` 能找到 Qt 菜单项。
- `alt+F4` 关闭 FDM 实测有效。

## 6. FGA / FBASIC 项目库对话框

| 症状 | 原因 | 处理 |
|---|---|---|
| `Database settings` 里填了 SQLite 路径，Tab 后内容被清空、`Ok` 变灰 | Qt 输入框没有提交/校验，直接打字不会被接受 | 点 `...` 走 Win32 `Open DB file`，在 `File name` 填绝对路径后点 `打开`；或用 `foran gui fill-db --project <db> --yes` |
| FGA/FBASIC 启动了，但脚本操作没有生效 | 项目库还没选，模块停在 `Database settings` 对话框 | 先选库；`foran fga ... --db <db>` / `foran fbasic ... --db <db>` 会自动填这个对话框 |
| `Incorrect type of view` 弹窗，脚本卡住 | 在 FGA 里 `Init` 了不存在的视图（`SrfView`/`EntView`/`StbView`/`EqpView`） | FGA 只用 `GspView`/`GsfView`/`CmpView` |
| `No item selected` | `GaNewDrawCmd`/`GaArrangeDrawCmd` 要求 GUI 树有选中项 | 先在 `General arrangements` 选项卡选中 `Ship`（新建图纸）或图纸子节点（Arrange） |
| `Bad item selected` | 选中了错误层级（如选中 Ship 却点 Arrange） | 选中具体图纸节点 |
| 退出 2D 时弹 “exit without save it?” | 绘图修改未保存 | 先 `File > Save drawing`，再 `File > Exit 2D context` |
| `foran ... \| tail` 在 GUI 启动后不返回 | 子进程继承了父进程 stdout 管道 | 已修：`foran_launch` 把子进程 stdio 重定向到 `_foran_work/logs/` |
| 已有 `fga.exe` 时自动化找不到 `Open DB file` | FGA 单实例/旧窗口挡住 | 先关闭；或 `--close-existing`（可能丢未保存工作） |

## 7. FORAN 计算/建模警告速查（2026-10-27 实测）

| 弹窗/日志 | 含义 | 处理 |
|---|---|---|
| `Warning: The ship's profile is not defined. Calculations will be much slower` | 项目的 External hull 下缺少 PROFILE 线（`CL`）；FBASIC 找不到 profile，只影响速度、不影响结果。常见于 `fga import-hull` 之后——该命令替换 External hull 时会删掉它的全部子线 | `foran fga import-hull` 现在会在导入前快照、导入后回填这些线；可用 `--no-restore-lines` 关闭。若旧库已出现，检查 `DSG_LINE_DATA` 是否有 `LINE_TYPE=4` 且父节点是 External hull |
| `No more than one solid hull can be created` | 已有 `SOLID-01` 时不能 `New Hull` | 右键 `SOLID-01 > Edit` 编辑现有实体；确需新建先 `Delete` |
| `Please provide a positive height!` | `Method=Height` 的高度仍为 0 | 点 `Height` 数值格 → `Ctrl+A` → 输入 `14.6` → `Enter`（确认显示 `14.600 m`）再 `Build WH` |
| `Watertigh hull sections are not calculated` | 静水力前没算水密船体剖面 | `SOLID-01 > Edit > Sections` → `Do you want to calculate the default sections?` → `Yes` → `Ok` → `File > Save` |
| `Surface External hull is already defined. Do you want to overwrite it with External hull?` | `Import Hull forms` 时项目里已有同名表面 | 在**数据库副本**上选 `Yes to All`；不要对原件操作 |
| `Undefined location for surface External Hull` | 导入的表面没有 Location | `Import surfaces > Edit` 里给表面设 `Location`（如 `/Ship`）；或使用 FSF 里已带 Location 的 `External hull` |
| `Information: Do you want to calculate the default sections?` | 生成 WH 后首次算剖面 | `Yes`；之后 `DSG_SOLID_HULL_SECTIONS` 才会 > 0 |
| `Information modified` | 关闭时项目有未保存修改 | `Yes` 保存；自动化里 `_close_fga` 会处理 |
| `Cannot commit transaction changes: database is locked`（FGA 导入时） | 另一个 FORAN 模块还开着**同一个库文件**（常见：`--keep-open` 的 FBASIC 停在即将被 `--copy` 覆盖的副本上） | 先关掉所有 FORAN 进程，再复制/导入；不要让 FBASIC 对着将要被覆盖的副本常开 |
| `Problem calculating longitudinal strength: LSW distribution not calculated` | 空船重量分布还没算过，或算完但当前会话仍用旧缓存 | 先做 **LSW → Edit complex distribution → OK → 接受 Remainder 警告 → File > Save**，确认 `DSG_LSW_DIST_RESULTS > 0`；然后**重启 FBASIC**，再 `Update` LC。分布写库后同一会话里仍会报该错，重启即消失 |
| `Invalid definition of grid cell widths`（LSW 右键 `Report`） | 报表发布模块（publish.qm）排版错误，不是 LSW 数据问题 | 不要用 `Report` 触发分布计算；按上一条走 `Edit complex distribution`。关闭该错误框可能导致 fbasic.exe 退出 |
| `Ship has not correctly assembled` | Build Ship 时 patch 还在 Work Space | Manager 里把 patch 逐个拖到 `External Hull` 后再 Finish |
| `The Frame system has not been defined` | Lines Drawing 前没定义肋位 | `File > Ship > Edit frame system` 设 `Nmax/Spc`，或 `fsf build` 的默认肋位 |

**`Method=Spaces` 的绿色 `+`** 不是没反应：它会打开 `Space selection` 对话框（Ship > CARGO > SPC-xxxx），勾选**闭合 BREP 导入的 space** 后 `OK`，`Build WH` 才能成功。开放壳（`makeSolid=False`）不要走这条。

## 8. 环境自检项

`foran env check` 会检查：

- 安装目录、bin、许可文件、conf、包装脚本；
- 四个模块的 wrapper/official/exe；
- 缺失项会标 `[X]`，警告标 `[!]`。

状态 `PROBLEMS` 时不要盲目启动，先按上面的路径逐项核对。
