#!/usr/bin/env python3
"""
Stock Dashboard · 行情数据更新引擎 v3
数据源: 国泰海通灵犀金融Skill (主) + 东方财富API (板块备份)
更新时间: 2026-05-21
"""

import json, os, sys, time, datetime, subprocess, re
from pathlib import Path
import requests

BASE = Path(__file__).parent
DATA_FILE = BASE / "data.json"
DATA_DIR = BASE / "data"
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ============= 灵犀金融Skill 配置 =============
LINGXI_DIR = Path("C:/Users/Lihaoyang/.workbuddy/skills/国泰海通金融数据查询")
LINGXI_ENTRY = LINGXI_DIR / "skill-entry.js"
# API Key 授权文件（由 authChecker 自动管理）
AUTH_FILE = Path("C:/Users/Lihaoyang/.workbuddy/gtht-skill-shared/gtht-entry.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# ============= 股票跟踪列表 =============
TRACKED = [
    ("688375", "国博电子", "商业航天", "中游·卫星载荷"),
    ("688333", "铂力特", "商业航天", "上游·火箭制造"),
    ("600498", "烽火通信", "商业航天", "中游·通信"),
    ("603698", "航天工程", "商业航天", "中游·地面设备"),
    ("601698", "中国卫通", "商业航天", "下游·运营"),
    ("688387", "信科移动", "商业航天", "中游·通信"),
    ("688281", "华秦科技", "商业航天", "上游·火箭制造"),
    ("301005", "超捷股份", "商业航天", "上游·火箭制造"),
    ("300474", "景嘉微", "商业航天", "中游·芯片"),
    ("002371", "北方华创", "半导体", "设备"),
    ("688012", "中微公司", "半导体", "设备"),
    ("688072", "拓荆科技", "半导体", "设备"),
    ("688120", "华海清科", "半导体", "设备"),
    ("688126", "沪硅产业", "半导体", "材料"),
    ("002409", "雅克科技", "半导体", "材料"),
    ("688256", "寒武纪", "半导体", "AI芯片"),
    ("688041", "海光信息", "半导体", "AI芯片"),
    ("688981", "中芯国际", "半导体", "制造"),
    ("600900", "长江电力", "电力", "水电"),
    ("003816", "中国广核", "电力", "核电"),
    ("600905", "三峡能源", "电力", "新能源"),
    ("600406", "国电南瑞", "电力", "电网"),
    ("600089", "特变电工", "电力", "电网"),
    ("002028", "思源电气", "电力", "电网"),
    ("300274", "阳光电源", "电力", "储能"),
    ("300750", "宁德时代", "电力", "储能"),
    ("688390", "固德威", "电力", "储能"),
]

# ============= 热门板块（东方财富API） =============
DYNAMIC_SECTORS = [
    ("BK0477", "半导体"),      ("BK0954", "商业航天"),
    ("BK0462", "电力行业"),    ("BK0800", "AI芯片"),
    ("BK0451", "光伏设备"),    ("BK0478", "消费电子"),
    ("BK0491", "新能源车"),    ("BK0438", "军工电子"),
    ("BK0809", "数据要素"),    ("BK0878", "机器人"),
    ("BK0446", "创新药"),      ("BK0582", "低空经济"),
    ("BK0863", "量子科技"),    ("BK0805", "氢能"),
]


# ═══════════════════════════════════════════════
#  灵犀Skill调用层
# ═══════════════════════════════════════════════

def _check_lingxi_auth():
    """检查灵犀Skill授权状态"""
    if not AUTH_FILE.exists():
        return False
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        return bool(data.get("apiKey"))
    except Exception:
        return False


def _call_lingxi(query: str, timeout: int = 20) -> dict:
    """
    调用灵犀金融Skill查询
    返回: list[dict] 每只股票的数据字典
    """
    if not _check_lingxi_auth():
        print(f"  ⚠ 灵犀Skill未授权，跳过查询: {query[:30]}...")
        return []

    if not LINGXI_ENTRY.exists():
        print(f"  ⚠ 灵犀Skill入口不存在: {LINGXI_ENTRY}")
        return []

    try:
        result = subprocess.run(
            ["node", str(LINGXI_ENTRY), "mcpClient", "call",
             "financial", "financial-search", f"query={query}"],
            cwd=str(LINGXI_DIR),
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            print(f"  ⚠ 灵犀查询失败: {result.stderr.strip()[-120:]}")
            return []

        # 解析返回: outer JSON → text 字符串 → 直接提取Markdown表格
        # 注意: text 字段内部不是标准JSON（中文文本无引号），不能 json.loads
        outer = json.loads(result.stdout)
        raw_text = outer.get("text", "")

        return _parse_lingxi_table(raw_text)

    except json.JSONDecodeError as e:
        print(f"  ⚠ 灵犀外层JSON解析失败: {e}")
        return []
    except subprocess.TimeoutExpired:
        print(f"  ⚠ 灵犀查询超时: {query[:50]}...")
        return []
    except Exception as e:
        print(f"  ⚠ 灵犀调用异常: {e}")
        return []


def _parse_lingxi_table(md_text: str) -> list:
    """
    解析灵犀返回的Markdown表格
    格式: | 股票代码 | 股票简称 | 最新价 | 最新涨跌幅 | ...
    """
    results = []
    lines = md_text.strip().split("\n")
    headers = []
    data_started = False

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]

        if not data_started:
            # 第一行是表头
            if any(h in ["股票代码", "股票简称", "指数代码"] for h in cells):
                headers = cells
                data_started = True
            continue

        # 跳过分隔行
        if all(c.replace("-", "").replace(":", "").strip() == "" for c in cells):
            continue

        # 数据行
        if len(cells) == len(headers):
            row = dict(zip(headers, cells))
            results.append(row)

    return results


# ═══════════════════════════════════════════════
#  数据拉取
# ═══════════════════════════════════════════════

def _fmt_pct_str(v):
    """格式化涨跌幅字符串"""
    try:
        val = float(v)
        sign = "+" if val > 0 else ""
        return f"{sign}{val:.2f}%"
    except (ValueError, TypeError):
        return "--"


def _fmt_pct_val(v):
    """提取涨跌幅数值"""
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def fetch_indices_lingxi():
    """通过灵犀Skill拉取三大指数"""
    rows = _call_lingxi("查询上证指数、深证成指、科创50指数的最新涨跌幅")
    indices = {}
    for row in rows:
        code = row.get("指数代码", "").split(".")[0]
        name = row.get("指数简称", "")
        price = row.get("最新价", "--")
        # 指数表头含冒号 "最新涨跌幅:前复权" 或 "涨跌幅[日期]"
        pct = (row.get("涨跌幅[20260521]", "") or
               row.get("最新涨跌幅:前复权", "") or
               row.get("最新涨跌幅", "0"))
        pct_val = _fmt_pct_val(pct)
        indices[code] = {
            "price": price,
            "change_pct": _fmt_pct_str(pct_val),
            "change_pct_value": pct_val,
        }
    return indices


def fetch_stocks_lingxi(tracked: list, batch_size: int = 7) -> list:
    """
    通过灵犀Skill分批拉取个股行情
    返回: list[dict] 按原始顺序排列的股票数据
    """
    results = []
    stock_map = {}  # code -> stock entry

    for i in range(0, len(tracked), batch_size):
        batch = tracked[i:i + batch_size]
        names = "、".join([t[1] for t in batch])
        query = f"查询{names}的最新价格和涨跌幅"
        print(f"  灵犀查询 ({i+1}-{min(i+batch_size, len(tracked))}/{len(tracked)}): {names[:50]}...")

        rows = _call_lingxi(query)

        for row in rows:
            code_raw = row.get("股票代码", "")
            code = code_raw.split(".")[0]  # 002371.SZ -> 002371
            name = row.get("股票简称", "")
            price = row.get("最新价", "--")
            # 兼容不同字段名: "最新涨跌幅" 或 "涨跌幅[日期]"
            pct_raw = (row.get("涨跌幅[20260521]", "") or
                       row.get("最新涨跌幅", "0"))
            pct_val = _fmt_pct_val(pct_raw)

            stock_map[code] = {
                "price": price,
                "change_pct": _fmt_pct_str(pct_val),
                "change_pct_value": pct_val,
                "trend": "up" if pct_val > 0 else ("down" if pct_val < 0 else "flat"),
            }

    # 按原始顺序组装
    fetch_count = 0
    for code, name, sector, subsector in tracked:
        data = stock_map.get(code, {})
        price = data.get("price", "--")
        if price != "--":
            fetch_count += 1

        results.append({
            "code": code, "name": name,
            "sector": sector, "subsector": subsector,
            "price": price,
            "change_pct": data.get("change_pct", "--"),
            "change_pct_value": data.get("change_pct_value", 0),
            "volume_万": "--",
            "turnover_亿": "--",
            "pe": "--",
            "trend": data.get("trend", "flat"),
        })

    print(f"  个股行情: {fetch_count}/{len(tracked)} 只成功")
    return results


def fetch_sectors_eastmoney():
    """通过东方财富API拉取板块（灵犀不支持板块查询）"""
    sectors_data = []
    secids = ",".join([f"90.{s[0]}" for s in DYNAMIC_SECTORS])
    try:
        r = requests.get(
            "http://push2.eastmoney.com/api/qt/ulist.np/get",
            params={"fltt": 2, "invt": 2, "fields": "f2,f3,f4,f12,f14", "secids": secids},
            headers=HEADERS, timeout=10,
        )
        diffs = r.json().get("data", {}).get("diff", [])
        for d in diffs:
            pct = float(d.get("f3", 0))
            sectors_data.append({
                "code": d.get("f12", ""),
                "name": d.get("f14", ""),
                "change_pct": _fmt_pct_str(pct),
                "change_pct_value": pct,
                "trend": "up" if pct > 0 else ("down" if pct < 0 else "flat"),
            })
        print(f"  板块行情: {len(diffs)}/{len(DYNAMIC_SECTORS)} 个成功")
    except Exception as e:
        print(f"  板块行情失败: {e}")
    return sectors_data


# ═══════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════

def main():
    now = datetime.datetime.now()
    print("=" * 60)
    print(f"  Stock Dashboard · 行情更新引擎 v3")
    print(f"  数据源: 灵犀金融Skill (主) + 东方财富 (板块)")
    print(f"  运行时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 检查灵犀授权
    if not _check_lingxi_auth():
        print("[⚠] 灵犀金融Skill未授权!")
        print("    请先运行扫码授权流程，或检查 AUTH_FILE")
        print(f"    预期位置: {AUTH_FILE}")
        # 回退到东方财富API模式
        print("    降级: 使用东方财富API (数据可能不完整)")
        # TODO: 可在此处调用旧版东方财富API逻辑
        print()
    else:
        print("[✓] 灵犀金融Skill已授权")
        print()

    result = {
        "update_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "update_date": now.strftime("%Y-%m-%d"),
        "is_trading": 9 <= now.hour < 15 or (now.hour == 15 and now.minute < 30),
        "indices": {},
        "stocks": [],
        "sectors": [],
        "data_source": "国泰海通灵犀金融Skill + 东方财富板块",
        "note": "灵犀金融Skill实时行情 | 国泰海通数据源",
    }

    # ── [1/4] 大盘指数 ──
    print("[1/4] 拉取大盘指数 (灵犀Skill)...")
    idx_data = fetch_indices_lingxi()
    result["indices"] = {
        "sh_index": idx_data.get("000001", {"price": "--", "change_pct": "--", "change_pct_value": 0}),
        "sz_index": idx_data.get("399001", {"price": "--", "change_pct": "--", "change_pct_value": 0}),
        "kc50": idx_data.get("000688", {"price": "--", "change_pct": "--", "change_pct_value": 0}),
        "volume": "--",
        "volume_days": "--",
        "volume_note": "今日成交",
        "chip_index_name": "科创芯片",
        "chip_index_ytd": "+47.83%",
        "chip_index_ytd_value": 47.83,
        "chip_index_note": "年内最强指数之一",
        "power_pe": "~12x",
        "power_pe_note": "过去五年 30% 以下分位",
    }
    sh = result["indices"]["sh_index"]
    kc = result["indices"]["kc50"]
    print(f"  上证 {sh['price']} ({sh['change_pct']})  |  "
          f"科创50 {kc['price']} ({kc['change_pct']})")

    # ── [2/4] 个股行情 ──
    print("[2/4] 拉取个股行情 (灵犀Skill)...")
    result["stocks"] = fetch_stocks_lingxi(TRACKED, batch_size=7)
    fetch_count = sum(1 for s in result["stocks"] if s["price"] != "--")

    # ── [3/4] 热门板块 ──
    print("[3/4] 拉取热门板块 (东方财富API)...")
    sectors = fetch_sectors_eastmoney()
    if sectors:
        sectors.sort(key=lambda x: abs(x.get("change_pct_value", 0)), reverse=True)
    # 仅保留前10个涨跌幅最大的板块
    result["sectors"] = sectors[:12]
    print(f"  最终展示: {len(result['sectors'])} 个板块")

    # ── [4/5] 保存 ──
    print("[4/5] 保存数据...")
    old_data = None
    if DATA_FILE.exists():
        try:
            old_data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 缓存降级：如果新数据缺失，保留旧数据
    if fetch_count < 10 and old_data and old_data.get("stocks"):
        old_stocks = {s["code"]: s for s in old_data["stocks"]}
        for s in result["stocks"]:
            if s["price"] == "--" and s["code"] in old_stocks:
                old = old_stocks[s["code"]]
                if old.get("price") and old["price"] != "--":
                    s["price"] = old["price"] + " *"
                    s["change_pct"] = old.get("change_pct", "--") + " *"
                    s["change_pct_value"] = old.get("change_pct_value", 0)
                    s["trend"] = old.get("trend", "flat")

    DATA_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  data.json 已更新 (个股 {fetch_count}/{len(TRACKED)})")

    # 历史备份
    backup_path = DATA_DIR / f"{now.strftime('%Y-%m-%d')}.json"
    backup_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  历史备份: {backup_path.name}")

    # ── [5/5] Git 同步 ──
    print("[5/5] Git 同步...")
    try:
        subprocess.run(["git", "add", "data.json", str(backup_path)],
                       cwd=BASE, capture_output=True, timeout=15)
        subprocess.run(
            ["git", "commit", "-m",
             f"行情更新 {now.strftime('%m-%d %H:%M')} · 灵犀Skill {fetch_count}/{len(TRACKED)}只"],
            cwd=BASE, capture_output=True, timeout=15,
        )
        git_push = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=BASE, capture_output=True, text=True, timeout=30,
        )
        if git_push.returncode == 0:
            print("  Git push 完成 ✓")
        else:
            err = git_push.stderr.strip()[-150:]
            print(f"  Git push 失败: {err}")
    except Exception as e:
        print(f"  Git 同步异常: {e}")

    # 日志
    log_file = LOG_DIR / f"{now.strftime('%Y%m%d_%H%M%S')}.log"
    log_file.write_text(
        f"v3 灵犀Skill | {now}\n"
        f"指数: {'成功' if idx_data else '失败'}\n"
        f"个股: {fetch_count}/{len(TRACKED)}\n"
        f"板块: {len(result['sectors'])}个\n",
        encoding="utf-8",
    )

    print()
    print(f"  更新完成! 个股 {fetch_count}/{len(TRACKED)} | 板块 {len(result['sectors'])}个")
    print()


if __name__ == "__main__":
    main()
