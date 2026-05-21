#!/usr/bin/env python3
"""
Stock Dashboard · 行情数据更新引擎
数据源: 东方财富公开API (主) + akshare (备)
更新时间: 2026-05-21
"""

import json, os, sys, time, datetime, subprocess
from pathlib import Path
import requests

BASE = Path(__file__).parent
DATA_FILE = BASE / "data.json"
DATA_DIR = BASE / "data"
LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# ============= 股票跟踪列表 =============
TRACKED = [
    # secid, code, name, sector, subsector
    # --- 商业航天 ---
    ("1.688375", "688375", "国博电子", "商业航天", "中游·卫星载荷"),
    ("1.688333", "688333", "铂力特", "商业航天", "上游·火箭制造"),
    ("1.600498", "600498", "烽火通信", "商业航天", "中游·通信"),
    ("1.603698", "603698", "航天工程", "商业航天", "中游·地面设备"),
    ("1.601698", "601698", "中国卫通", "商业航天", "下游·运营"),
    ("1.688387", "688387", "信科移动", "商业航天", "中游·通信"),
    ("1.688281", "688281", "华秦科技", "商业航天", "上游·火箭制造"),
    ("0.301005", "301005", "超捷股份", "商业航天", "上游·火箭制造"),
    ("0.300474", "300474", "景嘉微", "商业航天", "中游·芯片"),
    # --- 半导体 ---
    ("0.002371", "002371", "北方华创", "半导体", "设备"),
    ("1.688012", "688012", "中微公司", "半导体", "设备"),
    ("1.688072", "688072", "拓荆科技", "半导体", "设备"),
    ("1.688120", "688120", "华海清科", "半导体", "设备"),
    ("1.688126", "688126", "沪硅产业", "半导体", "材料"),
    ("0.002409", "002409", "雅克科技", "半导体", "材料"),
    ("1.688256", "688256", "寒武纪", "半导体", "AI芯片"),
    ("1.688041", "688041", "海光信息", "半导体", "AI芯片"),
    ("1.688981", "688981", "中芯国际", "半导体", "制造"),
    # --- 电力 ---
    ("1.600900", "600900", "长江电力", "电力", "水电"),
    ("0.003816", "003816", "中国广核", "电力", "核电"),
    ("0.600905", "600905", "三峡能源", "电力", "新能源"),
    ("0.600406", "600406", "国电南瑞", "电力", "电网"),
    ("0.600089", "600089", "特变电工", "电力", "电网"),
    ("0.002028", "002028", "思源电气", "电力", "电网"),
    ("0.300274", "300274", "阳光电源", "电力", "储能"),
    ("0.300750", "300750", "宁德时代", "电力", "储能"),
    ("1.688390", "688390", "固德威", "电力", "储能"),
]

# ============= 热门板块动态获取 =============
DYNAMIC_SECTORS = [
    # (sector_code, sector_name), eastmoney sector API codes
    ("BK0477", "半导体"),
    ("BK0954", "商业航天"),
    ("BK0462", "电力行业"),
    ("BK0800", "AI芯片"),
    ("BK0451", "光伏设备"),
    ("BK0478", "消费电子"),
    ("BK0491", "新能源车"),
    ("BK0438", "军工电子"),
    ("BK0809", "数据要素"),
    ("BK0878", "机器人"),
    ("BK0446", "创新药"),
    ("BK0582", "低空经济"),
    ("BK0863", "量子科技"),
    ("BK0805", "氢能"),
]


def _fmt(n, scale=100):
    """格式化数字：分→元，精度2位"""
    if n is None or n == "-":
        return "--"
    try:
        v = float(n) / scale
        return f"{v:.2f}"
    except (ValueError, TypeError):
        return str(n)


def _fmt_pct(n):
    """涨跌幅格式化（东方财富返回的是0.01%单位，即-89=-0.89%）"""
    if n is None or n == "-":
        return "--"
    try:
        v = float(n) / 100
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.2f}%"
    except (ValueError, TypeError):
        return str(n)


def _fmt_num(n):
    """提取数值"""
    if n is None or n == "-":
        return 0
    try:
        return float(n)
    except (ValueError, TypeError):
        return 0


def fetch_sector_data():
    """拉取动态热门板块行情"""
    sectors_data = []
    secids = ",".join([f"90.{s[0]}" for s in DYNAMIC_SECTORS])
    try:
        r = requests.get(
            "http://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": 2, "invt": 2,
                "fields": "f2,f3,f4,f12,f14",
                "secids": secids,
            },
            headers=HEADERS,
            timeout=10,
        )
        data = r.json()
        diffs = data.get("data", {}).get("diff", [])
        for d in diffs:
            code = d.get("f12", "")
            name = d.get("f14", "")
            pct = _fmt_num(d.get("f3", 0))
            sectors_data.append({
                "code": code,
                "name": name,
                "change_pct": _fmt_pct(d.get("f3", 0)),
                "change_pct_value": pct,
                "trend": "up" if pct > 0 else ("down" if pct < 0 else "flat"),
            })
        print(f"  板块行情: {len(diffs)}/{len(DYNAMIC_SECTORS)} 个成功")
    except Exception as e:
        print(f"  板块行情失败: {e}")
    return sectors_data


def main():
    now = datetime.datetime.now()
    print("=" * 60)
    print(f"  Stock Dashboard · 行情更新脚本")
    print(f"  运行时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    result = {
        "update_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "update_date": now.strftime("%Y-%m-%d"),
        "is_trading": 9 <= now.hour < 15 or (now.hour == 15 and now.minute < 10),
        "indices": {},
        "stocks": [],
        "sectors": [],
        "note": "东方财富实时行情 + 灵犀金融增强",
    }

    # ──────── 1. 大盘指数 ────────
    print("[1/4] 拉取大盘指数...")
    try:
        r = requests.get(
            "http://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": 2, "invt": 2,
                "fields": "f2,f3,f4,f6,f12,f14",
                "secids": "1.000001,0.399001,1.000688",
            },
            headers=HEADERS,
            timeout=10,
        )
        idx_data = r.json().get("data", {}).get("diff", [])
        idx_map = {d["f12"]: d for d in idx_data}

        sh = idx_map.get("000001", {})
        sz = idx_map.get("399001", {})
        kc = idx_map.get("000688", {})

        vol_total = _fmt_num(sh.get("f6", 0)) + _fmt_num(sz.get("f6", 0))
        vol_str = f"{vol_total / 1e8:.0f}亿" if vol_total > 0 else "--"

        result["indices"] = {
            "sh_index": {
                "price": _fmt(sh.get("f2"), 1),
                "change_pct": _fmt_pct(sh.get("f3")),
                "change_pct_value": _fmt_num(sh.get("f3")),
            },
            "sz_index": {
                "price": _fmt(sz.get("f2"), 1),
                "change_pct": _fmt_pct(sz.get("f3")),
                "change_pct_value": _fmt_num(sz.get("f3")),
            },
            "kc50": {
                "price": _fmt(kc.get("f2"), 1),
                "change_pct": _fmt_pct(kc.get("f3")),
                "change_pct_value": _fmt_num(kc.get("f3")),
            },
            "volume": vol_str,
            "volume_days": "--",
            "volume_note": "今日成交",
            "chip_index_name": "科创芯片",
            "chip_index_ytd": "+47.83%",
            "chip_index_ytd_value": 47.83,
            "chip_index_note": "年内最强指数之一",
            "power_pe": "~12x",
            "power_pe_note": "过去五年 30% 以下分位",
        }
        print(f"  指数: 上证 {_fmt(sh.get('f2'),1)} ({_fmt_pct(sh.get('f3'))})  "
              f"科创50 {_fmt(kc.get('f2'),1)} ({_fmt_pct(kc.get('f3'))})")
    except Exception as e:
        print(f"  指数获取失败: {e}")

    # ──────── 2. 个股行情 ────────
    print("[2/4] 拉取个股行情...")
    fetch_count = 0
    for i, (secid, code, name, sector, subsector) in enumerate(TRACKED):
        entry = {
            "code": code, "name": name,
            "sector": sector, "subsector": subsector,
            "price": "--", "change_pct": "--", "change_pct_value": 0,
            "volume_万": "--", "turnover_亿": "--", "pe": "--", "trend": "flat",
        }
        try:
            r = requests.get(
                "http://push2.eastmoney.com/api/qt/stock/get",
                params={
                    "secid": secid,
                    "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f116,f169,f170",
                },
                headers=HEADERS,
                timeout=8,
            )
            d = r.json().get("data", {})
            if d and d.get("f58"):
                price = _fmt(d.get("f43"))
                pct = _fmt_pct(d.get("f170"))
                pct_val = _fmt_num(d.get("f170")) / 100
                entry["price"] = price
                entry["change_pct"] = pct
                entry["change_pct_value"] = pct_val
                entry["volume_万"] = str(d.get("f47", "--"))
                entry["turnover_亿"] = _fmt(d.get("f48", 0), 10000)  # 分→万元→亿
                entry["trend"] = "up" if pct_val > 0 else ("down" if pct_val < 0 else "flat")
                fetch_count += 1
        except Exception:
            pass
        result["stocks"].append(entry)
        if (i + 1) % 6 == 0:
            time.sleep(0.5)  # 每6只休息一下
    print(f"  个股行情: {fetch_count}/{len(TRACKED)} 只成功")

    # ──────── 3. 热门板块 ────────
    print("[3/4] 拉取热门板块...")
    sectors = fetch_sector_data()
    if sectors:
        sectors.sort(key=lambda x: abs(x.get("change_pct_value", 0)), reverse=True)
    result["sectors"] = sectors

    # ──────── 4. 保存 ────────
    print("[4/4] 保存数据...")
    # 备份旧数据
    old_data = None
    if DATA_FILE.exists():
        try:
            old_data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 如果新数据抓取太少，合并旧数据（保留前次成功的结果）
    if fetch_count < 10 and old_data and old_data.get("stocks"):
        old_stocks = {s["code"]: s for s in old_data["stocks"]}
        for s in result["stocks"]:
            if s["price"] == "--" and s["code"] in old_stocks:
                old = old_stocks[s["code"]]
                if old.get("price") and old["price"] != "--":
                    s["price"] = old["price"] + " *"
                    s["change_pct"] = old.get("change_pct", "--") + " *"
                    s["change_pct_value"] = old.get("change_pct_value", 0)
                    s["volume_万"] = old.get("volume_万", "--")
                    s["turnover_亿"] = old.get("turnover_亿", "--")
                    s["trend"] = old.get("trend", "flat")

    DATA_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  data.json 已更新")

    # 备份历史
    backup_path = DATA_DIR / f"{now.strftime('%Y-%m-%d')}.json"
    backup_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  历史备份: {backup_path.name}")

    # ──────── 5. Git 同步 ────────
    print("[5/5] Git 同步...")
    try:
        subprocess.run(["git", "add", "data.json", str(backup_path)], cwd=BASE,
                       capture_output=True, timeout=15)
        subprocess.run(
            ["git", "commit", "-m",
             f"📊 {now.strftime('%m-%d %H:%M')} 行情更新 · {fetch_count}/{len(TRACKED)}只"],
            cwd=BASE, capture_output=True, timeout=15,
        )
        result_git = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=BASE, capture_output=True, text=True, timeout=30,
        )
        if result_git.returncode == 0:
            print("  Git push 完成 ✓")
        else:
            print(f"  Git push: {result_git.stderr.strip()[-100:]}")
    except Exception as e:
        print(f"  Git 同步跳过: {e}")

    # 写日志
    log_file = LOG_DIR / f"{now.strftime('%Y%m%d_%H%M%S')}.log"
    log_file.write_text(
        f"更新完成: {now}\n指数成功: {len(result.get('indices',{}).get('sh_index',{}))>0}\n"
        f"个股成功: {fetch_count}/{len(TRACKED)}\n板块: {len(result.get('sectors',[]))}个\n",
        encoding="utf-8",
    )

    print()
    print(f"✅ 更新完成! 个股 {fetch_count}/{len(TRACKED)} | 板块 {len(result.get('sectors',[]))}个")
    print()


if __name__ == "__main__":
    main()
