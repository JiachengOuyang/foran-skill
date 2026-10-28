# -*- coding: utf-8 -*-
"""List, parse and summarise FORAN journal logs (*.jrnl.csv).

FORAN writes a semicolon-separated journal with a variable number of
Data/Value pairs:
    Type;Timestamp;Data 1;Value 1;Data 2;Value 2;...
Typical Types: HEADER, DLGMESSAGE, COMMAND, MESSAGE.

Examples:
  python foran_journal.py list
  python foran_journal.py summary --latest
  python foran_journal.py summary "D:\\software\\school\\foran\\logs\\xxx.jrnl.csv" --errors
  python foran_journal.py tail --latest -n 20
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import foran_env as E  # noqa: E402

ERROR_TYPES = ("ERROR", "ERR", "WARNING", "WARN", "FAIL", "FATAL", "DLGMESSAGE")
ERROR_WORDS = re.compile(
    r"error|fail|invalid|not found|cannot|unable|refused|denied|corrupt|locked|missing|"
    r"警告|错误|失败|无效|找不到|拒绝|锁定",
    re.I,
)


def log_dirs(extra=None):
    dirs = [Path(extra).expanduser()] if extra else []
    dirs += [E.LOGS_DIR, E.USER_JOURNAL_DIR]
    seen, out = set(), []
    for d in dirs:
        try:
            r = d.resolve()
        except Exception:  # noqa: BLE001
            r = d
        if r not in seen:
            seen.add(r)
            out.append(d)
    return out


def find_logs(extra=None, include_user=True):
    found = []
    for d in log_dirs(extra):
        if d.is_dir():
            found.extend(sorted(d.glob("*.jrnl.csv"), key=lambda p: p.stat().st_mtime, reverse=True))
            if include_user:
                found.extend(sorted(d.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True))
    # de-duplicate, newest first
    uniq = {p.resolve(): p for p in found if p.is_file()}
    return sorted(uniq.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def parse(path: Path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        rd = csv.reader(f, delimiter=";")
        for raw in rd:
            if not raw or not raw[0].strip():
                continue
            if raw[0].strip().lower() == "type":
                continue  # column header line
            typ = raw[0].strip()
            ts = raw[1].strip() if len(raw) > 1 else ""
            fields = {}
            i = 2
            while i + 1 < len(raw):
                k = raw[i].strip()
                v = raw[i + 1].strip()
                if k:
                    fields[k] = v
                i += 2
            # one trailing value without a label
            if i < len(raw) and raw[i] and not fields:
                fields["_value"] = raw[i].strip()
            rows.append({"type": typ, "timestamp": ts, "fields": fields})
    return rows


def is_error(row) -> bool:
    if row["type"].upper() in ERROR_TYPES:
        return True
    text = " ".join([row["type"], *row["fields"].keys(), *row["fields"].values()])
    return bool(ERROR_WORDS.search(text))


def fmt_row(row) -> str:
    body = "  ".join(f"{k}={v}" for k, v in row["fields"].items())
    return f"{row['timestamp']}  {row['type']:<12} {body}".rstrip()


def cmd_list(a) -> int:
    logs = find_logs(a.dir)
    if a.json:
        print(json.dumps([{"path": str(p), "size": p.stat().st_size,
                           "mtime": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
                          for p in logs], ensure_ascii=False, indent=2))
        return 0
    if not logs:
        print("no journal logs found in: " + ", ".join(str(d) for d in log_dirs(a.dir)))
        return 1
    for p in logs[:a.limit]:
        st = p.stat()
        print(f"{dt.datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}  {st.st_size:8d}  {p}")
    return 0


def _pick(a):
    if a.file:
        p = Path(a.file).expanduser().resolve()
        if not p.exists():
            raise SystemExit(f"log not found: {p}")
        return p
    logs = find_logs(a.dir)
    if not logs:
        raise SystemExit("no journal logs found")
    return logs[0]


def cmd_summary(a) -> int:
    p = _pick(a)
    rows = parse(p)
    header = next((r["fields"] for r in rows if r["type"].upper() == "HEADER"), {})
    counts = {}
    for r in rows:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    problems = [r for r in rows if is_error(r)]
    out = {
        "file": str(p),
        "header": header,
        "rows": len(rows),
        "types": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "problems": problems,
    }
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"journal : {p}")
    print(f"rows    : {len(rows)}")
    if header:
        print("header  : " + "  ".join(f"{k}={v}" for k, v in header.items()))
    print("types   : " + "  ".join(f"{k}={v}" for k, v in out["types"].items()))
    print()
    if problems:
        print(f"problems ({len(problems)}):")
        for r in problems:
            print("  " + fmt_row(r))
    else:
        print("problems: none")
        for r in rows[-a.tail:]:
            print("  " + fmt_row(r))
    return 0


def cmd_tail(a) -> int:
    p = _pick(a)
    rows = parse(p)
    for r in rows[-a.n:]:
        print(fmt_row(r))
    return 0


def cmd_errors(a) -> int:
    p = _pick(a)
    rows = [r for r in parse(p) if is_error(r)]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("no errors/warnings matched")
        return 0
    for r in rows:
        print(fmt_row(r))
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("list", cmd_list), ("summary", cmd_summary), ("tail", cmd_tail), ("errors", cmd_errors)):
        p = sub.add_parser(name)
        p.add_argument("file", nargs="?")
        p.add_argument("--dir", help="extra directory to search")
        p.add_argument("--latest", action="store_true", help="use the newest log (default when FILE is omitted)")
        p.add_argument("--json", action="store_true")
        p.set_defaults(fn=fn)
        if name == "list":
            p.add_argument("--limit", type=int, default=20)
        if name == "summary":
            p.add_argument("--errors", action="store_true", help="(default) show only problems")
            p.add_argument("--tail", type=int, default=10, help="rows to show when no problems")
        if name == "tail":
            p.add_argument("-n", type=int, default=20)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
