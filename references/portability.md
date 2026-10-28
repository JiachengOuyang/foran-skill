# 换机器 / 换分辨率验证清单

本技能目前在 **1920×1080、150% 缩放、单机许可、示例项目库** 上实测通过。
大部分导航已按 UIA 结构定位，但仍有一小部分坐标是按这一布局量取的。换机器时按本清单逐项确认。

## 1. 先跑自检

```bash
S=foran
$S selftest --gui --fbasic "C:/FORAN/projects/sample.db"
```

- `display` 项会打印物理分辨率与缩放；不是 `1920x1080` 时会有 WARN 提示。
- `gui-smoke`：FDM 启动 → 主窗口 → 关闭。
- `fsurf-smoke`：FSURF 启动 → 主窗口 → 关闭（不需要库）。
- `fbasic-smoke`：复制库 → 启动 FBASIC → 选库 → **Calculations 树可见** → 关闭。

## 2. 再跑三条代表性 GUI 流程

按“从轻到重”跑，任何一条失败就先停下排查：

```bash
$S fbasic hydro --db sample.db --copy --calc HYD-CALC-01
$S fbasic lsw   --db sample.db --copy --tsv zones.tsv
$S fga brep     --db sample.db --copy --box 5,5,5 --node CARGO
$S fsf build    --brep hull_shell.brep --fnam TEST --lpp 172 --breadth 28.8 \
                --draught 9.83 --depth 14.6 --out out/TEST.fsf
```

## 3. 哪些地方仍是坐标依赖

| 位置 | 文件 | 说明 |
|---|---|---|
| FDM `File` 菜单与菜单项 | `foran_fdm.py` | 自绘菜单栏：UIA 不暴露，`Alt/F10/Alt+F` 实测也无效；只能点 `(55,40)` 打开 File，条目按 QPopup 相对偏移点 |
| FGA 出图（菜单栏） | `foran_fga.py` | 打开 `Tools` / 2D `File` 菜单栏仍按窗口相对坐标；菜单项（New/Arrange drawing、Save as、Save drawing、Exit 2D context）已按 UIA 名称（popup-first）点击 |
| `_click_calc_tab` 最后兜底 | `foran_fbasic.py` | UIA 与 OpenCV 都失败时才点 `(25,320)` |
| FDM Export 对话框控件 | `foran_fdm.py` | Qt 自绘，按对话框矩形相对坐标（比例不变，缩放改变时仍需核对） |

其余（停靠标签、树节点、菜单项、File>Save/Exit、数值格、LSW 下拉、LC 编辑器按钮）均已 UIA 化。

## 4. 重新量取的方法

1. 截屏留底：
   ```bash
   $S gui screenshot --window "fbasic -" --out out/fbasic.png
   ```
2. 枚举控件（先 UIA，找不到再 win32）：
   ```bash
   $S gui controls --window "fbasic -" --backend uia > out/controls.txt
   ```
3. 只在**已知控件**上验证一次点击，再批量操作；屏幕 150% 缩放时注意截图是物理像素（`pyautogui` 导入后会设置 DPI 感知，坐标即物理像素）。
4. 改完坐标后，至少跑 `selftest --gui` 加对应的一条业务流程。

## 5. 环境路径

安装位置/许可/日志/项目目录由 `config.toml` 的 `[foran]` 段或 `FORAN_SKILL_*` 环境变量提供（见 `installation.md`），不需要改代码。
