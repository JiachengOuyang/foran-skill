# FORAN 安装、许可与启动（通用版）

> 本文不含任何真实主机名、许可文件或本机路径。所有值由用户在自己的
> `config.toml` 或环境变量中提供。

## 1 前提

- Windows 10/11，已安装 **FORAN V80R3.0**（或兼容版本），并有有效许可。
- Python 3.10+；GUI 自动化另需 `requirements.txt` 中的依赖。
- 你**不能**把 FORAN 安装包、许可文件或帮助文档随本仓库分发。

## 2 配置

复制 `config.example.toml` 为 `config.toml`，填写：

```toml
[foran]
install_dir = "C:/Program Files/FORAN/V80R3.0"
wrapper_dir = ""                 # 可选：你自己的启动 bat 目录
license_file = ""                # 可选：本地 .lic；留空则用系统 LM_LICENSE_FILE
projects_dir = "C:/FORAN/projects"
workdir = "."
```

也可用环境变量覆盖：

| 变量 | 含义 |
|---|---|
| `FORAN_SKILL_INSTALL_DIR` | FORAN 安装根目录 |
| `FORAN_SKILL_WRAPPER_DIR` | 你自己的 .bat 包装目录（可选） |
| `FORAN_SKILL_LICENSE_FILE` | 本地 `.lic` 路径（可选） |
| `FORAN_SKILL_PROJECTS_DIR` | 项目库目录 |
| `FORAN_SKILL_WORKDIR` | 默认工作目录 |
| `FORAN_SKILL_CONFIG` | `config.toml` 路径 |

## 3 许可

FORAN 通过 FlexLM 类许可运行。两种常见方式：

1. **系统环境变量**：把 `LM_LICENSE_FILE` 指向你的许可（`.lic` 文件或
   `port@host`），由用户自己在系统/启动脚本里设置；
2. **本技能配置**：在 `config.toml` 的 `license_file` 填写 `.lic` 路径，
   `foran launch` 只在子进程里设置，不改全局值。

> 不要把许可文件提交到仓库；不要在本仓库的示例/文档里写真实主机名或端口。
> 若系统里同时存在 MSC 等其他 FlexLM 许可，建议只对 FORAN 子进程覆盖
> `LM_LICENSE_FILE`，避免影响其他软件。

## 4 启动

技能不直接运行 `.exe`，而是调用官方 `.bat` 链（会设置 `FORAN_HOME`、
`TCL_LIBRARY`、`MARRUNB`、`FORANDISK` 等）：

```bash
# 使用 config.toml 中的 install_dir / wrapper_dir
foran launch fsurf
foran launch fbasic --project /path/to/project.db --copy-project ./work/projects
```

若你有自己的包装 bat（推荐，便于固定许可和 conf），把 `wrapper_dir` 指向它。

> **重要：** 官方 bat 默认 `FORANDISK=C:\FORAN`。如果 FORAN 装在
> `C:\Program Files` 下，直接调用官方 bat 会报 “系统找不到指定的路径”
> 或 “FORAN user was not specified”。在 Windows 上请把 `wrapper_dir`
> 指向一个可用的包装目录（其中的 `fsurf.bat` / `fbasic.bat` / `fga.bat`
> 设置 `LM_LICENSE_FILE`、`FORAN_CONF` 和所需的启动参数）。
否则使用安装目录下的官方 bat。

## 5 自检

```bash
foran env check
foran env paths
foran selftest --db /path/to/project.db
```

- `env check` 会明确报告 `install_dir` 未配置、launcher 缺失、许可文件未配置等；
- 未配置许可时只给 warning，依赖你系统已有的 `LM_LICENSE_FILE`；
- 自检不会修改任何项目库。

## 6 常见问题

| 现象 | 处理 |
|---|---|
| `install_dir not configured` | 填 `config.toml` 或设 `FORAN_SKILL_INSTALL_DIR` |
| 模块窗口出现但打不开库 | 检查 `--project` 是否是 FORAN SQLite 库；先 `foran db check` |
| 许可报错 | 确认 `license_file` 或系统 `LM_LICENSE_FILE` 指向有效许可 |
| 多版本 FORAN | 用 `install_dir` 明确指向要用的版本 |
