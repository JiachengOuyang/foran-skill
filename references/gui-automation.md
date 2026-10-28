# GUI 自动化与分辨率校准

本技能的 GUI 自动化优先用 **UIA 结构定位**（按控件名/标签找），只有少数自绘菜单
或 Qt 表格需要回退到坐标。换机器/换分辨率时，先按本文校准，不要直接盲点。

## 1 三层定位

1. **UIA 控件**：按钮、输入框、树节点、下拉项——首选，和分辨率无关。
2. **窗口相对坐标**：自绘菜单栏、某些 Qt 弹出框——按窗口矩形偏移，缩放变化时要复核。
3. **模板匹配**：`foran vision` 用截图找图标（OpenCV），适合自绘标签页。

## 2 屏幕与 DPI

- 坐标按 **1920×1080 最大化窗口** 校准；截图是物理像素。
- `pyautogui` 在本仓库导入后会启用 DPI 感知，坐标按物理像素使用。
- Windows 150% 缩放时，逻辑坐标 = 物理坐标 ÷ 1.5；不要把截图坐标直接当逻辑坐标。
- `foran selftest` 的 `display` 项会打印分辨率；非 1920×1080 会 WARN。

## 3 校准流程

```bash
# 1) 截屏，确认当前界面
foran gui screenshot --window "fbasic -" --out ./out/fbasic.png

# 2) 枚举控件（先 UIA，再 win32）
foran gui controls --window "fbasic -" --backend uia > ./out/controls.txt

# 3) 选一个已知控件做一次验证点击（必须显式 --yes）
foran gui click --window "fbasic -" --name "Calculations" --yes

# 4) 确认无误后，再跑对应业务流程
foran fbasic hydro --db ./work/projects/sample_copy.db --copy
```

## 4 仍依赖坐标的地方

| 模块 | 位置 | 说明 |
|---|---|---|
| FDM | `File` 菜单及菜单项 | 自绘菜单栏，UIA 不暴露；按窗口相对坐标 |
| FGA | 2D 出图菜单栏 | 菜单栏按坐标，菜单项已尽量按 UIA 名称 |
| FBASIC | `Calculations` 标签兜底 | UIA/视觉匹配都失败时才点固定位置 |
| FDM | Export 对话框 | Qt 自绘，按对话框矩形比例 |

其余（停靠标签、树节点、File>Save/Exit、数值格、下拉框）已 UIA 化。

## 5 安全规则

- `foran gui click/type/keys` 默认拒绝执行，必须 `--yes`。
- 每次点击/输入前先截屏；失败立即停下报告，不要连续盲试。
- 需要用户确认时，把终端置顶，避免 FORAN 窗口挡住等待提示。
- 不改原始项目库；需要写入时先 `foran db copy`。
