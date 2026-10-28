# FORAN 日志（journal）格式与用法

## 1. 位置

| 位置 | 说明 |
|---|---|
| `C:/FORAN\logs\*.jrnl.csv` | 本机包装脚本 + 本地 `FORAN_CONF` 指定 |
| `%USERPROFILE%\.foran\journal\*.jrnl.csv` | FORAN 用户目录，通常也有一份 |

文件名形如：

```text
license-server_v80R3.0_fbasic_2026-10-12-144451.jrnl.csv
<主机>_<版本>_<模块>_<YYYY-MM-DD-HHMMSS>.jrnl.csv
```

## 2. 格式

分号分隔、UTF-8（可能带 BOM）、第一行是动态表头：

```csv
"Type";"Timestamp";"Data 1";"Value 1";"Data 2";"Value 2";...
"HEADER";"2026-10-12T14:44:51+0800";"build";"2020.01";"host";"license-server";"module";"fbasic";...
"DLGMESSAGE";"2026-10-12T14:45:14+0800";"message";"Invalid database file."
```

- 每行至少两列：`Type`、`Timestamp`。
- 之后是成对的 `Data N` / `Value N`；不同事件字段数不同。
- 常见 `Type`：
  - `HEADER`：会话信息（build/host/module/revision/version/platform/customer）。
  - `COMMAND_START` / `COMMAND_END`：命令执行。
  - `DLGMESSAGE`：对话框/提示消息（错误常在这里）。
  - `MESSAGE`：普通消息。
  - `ERROR` / `WARNING`：视模块而定。

## 3. 用 skill 读

```bash
S=foran

$S journal list
$S journal summary --latest
$S journal summary --latest --json
$S journal errors --latest
$S journal tail --latest -n 30
$S journal summary "C:/FORAN\logs\xxx.jrnl.csv"
```

`summary` 会输出：

- 会话 `HEADER`；
- 各 `Type` 计数；
- 命中错误/警告的行（`DLGMESSAGE` 一律列出，便于看 `Invalid database file.`、`Database locked` 等）。

## 4. 解读要点

| 日志 | 含义 | 处理 |
|---|---|---|
| `HEADER ... module=fbasic` | 本次是 FBASIC 会话 | 对照模块判断 |
| `DLGMESSAGE message=Invalid database file.` | 选错/损坏的项目库 | 见 troubleshooting |
| `DLGMESSAGE message=Database ... is locked` | 库被占用/只读 | 复制到本地再开 |
| `WinSock: Connection refused` | 许可服务器连不上 | 检查 `LM_LICENSE_FILE` |
| `Journal folder does NOT exist` | `FORAN_CONF` 没生效 | 用包装脚本 |
| `HOLTROP ... angle ... 0 deg to 90 deg` | 计算参数越界 | 业务参数问题，不是启动失败 |

## 5. 注意

- 日志是覆盖/滚动写入的：`FilesToKeepLocally=5`，本地只留最近几份；需要留证时先复制出来。
- 日志可能包含主机名、路径、项目名；外发/截图前确认是否需要脱敏。
- `journal list` 同时扫描本地 logs 和用户 journal；同名文件按路径去重，按 mtime 倒序。
