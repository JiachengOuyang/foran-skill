# FDM — FORAN Document Manager

FDM 是 FORAN 的文档查看/导出模块，**不连接项目库**（启动器不带 `-sqlite`），用于打开其他模块生成的 `.fds` 文档：报告、图、表格。

## 1. 启动

```bash
S=foran
$S launch fdm --workdir ".\_foran_work\fdm"
```

- 不需要 `.db`；给了 `--project` 也会被忽略（启动器会提示）。
- 直接进 `FORAN Document Manager` 主界面。

## 2. 文件格式

| 扩展名 | 含义 |
|---|---|
| `.fds` | FORAN Document（文档主格式，可打印/查看/导出） |
| `.fdx` | FORAN Document XML（另存格式） |
| `.dxf` | AutoCAD 交换格式（导出目标） |
| `.pdf` / Office | 导出目标 |

## 3. 菜单

### File

| 命令 | 作用 |
|---|---|
| `Open` | 打开 `.fds`（可同时开多份） |
| `Close active` / `Close selected` | 关闭当前/选中文档 |
| `Save active as` | 另存为 `.fds` 或 `.fdx` |
| `Export active` / `Export Selected` | 导出当前/选中文档（Office、DXF、PDF 等） |
| `Printer setup` / `Print active` / `Print selected` | 打印设置与打印 |
| `Join fds files` | 合并多个 `.fds` 为一个；不能合并不同页面方向 |
| `Recent Files` | 最近文件 |
| `Exit` | 退出（未保存的改动会丢失） |

### View

| 命令 | 作用 |
|---|---|
| `Zoom` / `Zoom in` / `Zoom out` | 缩放 |
| `Show document list` | 左侧文档列表：Act（眼睛=当前）、Orient、File、Title、Date；选中后可批量关闭/导出/打印 |

### Document

| 命令 | 作用 |
|---|---|
| `Document Properties` | 文档属性（需先打开文档） |
| `Styles` | 字体/标题/样式；DXF/PDF 使用打印机样式，不支持斜体/粗体/删除线/下划线 |

### Find

`Find`：在文档中查找；支持 `wrap`（从头继续）、`Match case`（区分大小写）、向上/向下。

### Help

`Help About` 打开完整在线帮助；`About FDM` 显示版本、系统、分辨率、模块日期、项目名、工作目录。

## 4. 导出注意

`File > Export active...` 的 `Files of type` 实测有 **7 种**（不是只有图片）：

| 序号 | 类型 | 输出 |
|---|---|---|
| 1 | DOCX (Microsoft OOXML) | `.docx`（ZIP/OOXML） |
| 2 | PDF (Portable Document Format) | `.pdf` |
| 3 | CSV (Comma Separated Values) | `.csv`（表格文本） |
| 4 | DXF (Drawing eXchange Format) | `.dxf` |
| 5 | ODT (Open Document Text) | `.odt` |
| 6 | Portable network graphics | `.png` |
| 7 | Scalable Vector Graphics | `.svg` |

- **Office**：导出 Word 需要 .NET Framework 3.5 SP1；查看 ODT 需要 Open Office。图片左边距可能被忽略，导致图片右移；单元格文字可能换行。
- **DXF**：PNG/SVG 不能嵌入 DXF，会生成同名 `_files` 文件夹；编辑 DXF 需要 AutoCAD。某些字符可能丢失；表格文字可能跑出表格。用 FSYSD 打开时 SVG 可显示。
- **PDF**：查看需要 Acrobat Reader 5.0+；样式取打印机样式。
- **PNG/SVG**：选完类型后还会弹 `Save as image`：`Resolution (dpi)` + `Current page` / `All pages`。`All pages` 会按 `<name>-001.ext`、`-002`… 逐页输出（275 页 sample 约 22 s、275 个文件）。
- **PNG 依赖页面渲染**：页视图空白时 FDM 弹 `Image file generation failed` 并留下 0 字节文件。本机 `sample.fds` 的页视图就是空白（PDF/DXF/CSV 仍能导出内容），所以 PNG 在此样本上必然失败；SVG 能出文件但同样是空页。需要位图时先确认页视图能显示内容。

## 5. 常见用法

```text
1) FBASIC/FGA/FSURF 里生成报告/图 → 输出 .fds
2) 打开 FDM → File > Open → 选 .fds
3) View > Show document list 管理多份文档
4) File > Export active → 选 DXF/PDF/Office
5) File > Join fds files 合并多份报告
```

## 6. 注意

- FDM 只读文档，不改项目库；但它打开的文件可能被其他模块占用，导出前确认源模块已保存。
- `.fds` 是二进制/专用格式，不要用文本编辑器改；要程序化处理请导出 DXF/CSV/PDF。
- 大批量导出用 `Export Selected`，先在 `Show document list` 里多选。

## 7. 自动化状态（2026-10-27）

- **`foran fdm open --fds <file>` 已实现并通过**：启动 FDM → `File > Open...` → 在 Win32 `Choose a document to open` 里填路径 → 校验窗口标题变为 `FORAN Document Manager - <file>`；`--screenshot` 可保存 PNG。
- FDM 主窗口的 MenuBar/ToolBar 暴露 UIA（`Open`、`Export active` 等），但 File 下拉的 QPopup 菜单项**不暴露** UIA，菜单操作用坐标；`Open` 文件对话框是 Win32 `#32770`，可自动化。
- **`foran fdm export --fds <file> --out <path> [--format ...] [--pages current|all]` 已实现并通过**：

```bash
S=foran
$S fdm export --fds _foran_work/fdm/sample.fds --out _foran_work/fdm/export_cli/sample.pdf
$S fdm export --fds report.fds --out page.svg --pages current
$S fdm export --fds report.fds --out all.svg --pages all
```

  - 格式由 `--out` 扩展名推断，可用 `--format` 覆盖：`docx/pdf/csv/dxf/odt/png/svg`。
  - 实测（sample.fds）：PDF 29,302 B（`%PDF-1.4`）、DOCX 2,969 B（PK）、CSV 434 B、DXF 40,987 B、ODT 3,685 B（PK）、SVG 839 B；PNG 因页视图空白报 `Image file generation failed`（退出码 1，脚本会删掉 0 字节残留）。
  - `--pages all` 实测 275 页 SVG 在 ~22 s 内输出 `all-001.svg`…`all-275.svg`。
- **Export 对话框的控件位置**（Qt 自绘，UIA 只有 Custom，只能按对话框矩形相对坐标）：
  - `File name`：`(left+372, top+432)`；`Files of type`：`(left+372, top+474)`；`Open`：`(left+643, top+432)`；`Cancel`：`(left+643, top+471)`。
  - 格式下拉的列表项**点击会穿透**（popup 是 click-through），不能点行；正确做法：点下拉 → `Esc` → `Down` × N（N = 上表序号），COMBO 每次重新打开都回到 DOCX。
  - `Save as image` 对话框：`Current page` `(left+35, top+106)`、`All pages` `(left+195, top+106)`、`Ok` `(left+93, top+147)`。
- **菜单栏只能用鼠标**：实测 `Alt`、`F10`、`Alt+F` 都不会打开 FDM 的 File 菜单（自绘菜单栏，UIA 也不暴露）。可靠做法仍是点击窗口左上菜单栏 `(55,40)`，再按 QPopup 相对偏移点条目。
- `.fds` 样本：`_foran_work/fdm/sample.fds`（由 FBASIC Tonnage `Report` 生成）。
- `Join`/`Print`/`Print selected` 仍未自动化；`Export Selected`（多文档）也未自动化。
