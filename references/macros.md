# FORAN 宏与命令脚本（FCS）

## 1. 是什么

- FORAN 的 **FCS（FORAN Command System）** 提供基于 **Tcl** 的宏语言。
- 可以录制/编写宏，把一串命令和参数保存成 ASCII 文件，之后从菜单一次执行。
- 菜单定义也走 ASCII 配置；安装目录里的 `*.mnu` 是编译后的菜单数据，**不要手改**。

官方帮助（官方帮助）明确写了：

> Macro programming language: the FCS allows the user to customise the system by means of a macro programming language based on Tcl.

> The Macros command really works as a menu, showing like commands all the user-made scripts, stored in any of the proper files. ... This is the only way to run the macros.

> Macro files are searched for in the working directory as the default option, although other folders can be reached by using the files browser.

## 2. 菜单路径

```text
Tools > Macros > Macros recorder   # 录制：边操作边生成脚本
Tools > Macros > Macros editor     # 编辑：打开已有宏文件，或从零写
Tools > Macros > Refresh menu      # 刷新：让新宏出现在菜单里
Tools > Macros > <宏名>            # 运行
```

## 3. 录制流程（最可靠）

1. 用包装快捷方式打开目标模块（`fbasic` / `fga` / `fsurf` / `fdm`）。
2. `Tools > Macros > Macros recorder`。
3. 给宏命名；选择已有或新建文件；文件非空时会问是否继续（YES 追加）。
4. 正常速度做一遍要自动化的操作。
5. 图形区右上角图标可：加注释（只在编辑器里可见）、加运行提示、结束录制。
6. `Tools > Macros > Refresh menu`。
7. 从 `Tools > Macros > <宏名>` 运行。

> 录制时的**工作目录**决定宏文件位置。快捷方式的 Start in 是 `.`；用 `foran launch ... --workdir <dir>` 可以改。

## 4. 文件与扩展名

- 宏是 **ASCII/Tcl** 文本，可手动编辑。
- 官方帮助没有写死扩展名；安装目录里有空的 `fbasic.mac`、`fga.mac`、`fsurf.mac` 占位文件，因此本 skill 默认按 **`.mac`** 管理。
- **待核实**：录制器实际生成的后缀可能是 `.mac` 或其他；以第一次录制出来的文件为准，不要强行改后缀。
- 宏文件默认在工作目录；编辑器里也可以浏览到其他目录。

## 5. skill 辅助

```bash
S=foran

$S macro where
$S macro list --workdir "."
$S macro new load_surface --workdir "." --note "加载型线"
$S macro show ".\load_surface.mac"
$S macro record-help
```

`macro new` 只生成带 Tcl `#` 注释头的 ASCII 骨架，**不会运行宏**。真正的命令序列应来自录制器；确认语法前不要凭空编写 FCS 命令。

## 6. 能做什么 / 不能做什么

适合：

- 重复性的建模/编辑步骤（同一套操作在多个项目上重放）。
- 记录一次成功操作，作为下一次的“脚本模板”。
- 把参数化的命令序列保存下来，减少手工点击。

不适合/有风险：

- **没有文档化的无头（headless）运行方式**：本机 V80R3.0 的宏只能从 GUI 的 `Tools > Macros` 运行。
- 不要直接双击 `.mac` 文件，它不会执行。
- 宏会在当前项目库上执行；**先在库副本上试**。
- 不要手改 `*.mnu`（编译后的菜单），也不要把宏文件当配置改系统路径。

## 7. 与 GUI 自动化的取舍

| 方式 | 优点 | 缺点 |
|---|---|---|
| 录制宏 | 官方支持、可重复、参数可编辑 | 需要先手动录一遍；无 headless |
| `foran gui`（pywinauto/pyautogui） | 可跨模块、可截屏核对 | 控件识别受 Qt 限制；坐标点击脆弱 |

优先宏；宏覆盖不到或只是“点几下看看”时，再用 `foran gui`，并且每步截图确认。

## 8. 命令名从哪查

- 官方帮助可在各模块的 Help 菜单中打开（本仓库不分发帮助文件）。
- `FGA/`、`fsurf/`、`fdm/`、`FBASIC/` 下每个 HTML 基本对应一个菜单命令，标题就是命令名。
- 命令参考见本 skill 的 `references/modules/*.md`。
- 不要从编译后的 `.mnu` 里猜语法；需要精确命令时，用录制器录一条最短的操作，观察生成的文本。
