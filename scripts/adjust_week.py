#!/usr/bin/env python3
"""每日 8:00 動態補量（2026-10-09 09:44 使用者確認）：本週跑量不足時，直接改本週「還沒跑」的跑步日公里數。
由 update_dashboard.py 在產生 plan.json 之前自動呼叫 apply()（activities.csv 要先補齊）；也可單獨執行：python3 adjust_week.py [YYYY-MM-DD]。
規則：
- 實際＝本週（週一起）今天（含）以前 Strava Run km（activities.csv）；剩餘＝今天起還沒跑的跑步日原計畫 km（今天已有 Run 就算已跑）。
- 差額＝週目標（make_plan.WEEK_TOTAL）−實際−剩餘；> 0 時依日期先後加到剩餘的輕鬆跑日（不含長跑、節奏、間歇、目標配速、測試、配速模擬、比賽），
  每天最多比原計畫 +3.0 km（CAP），km 取 0.01；配速／跑步機速度沿用該日原本的（輕鬆／恢復配速）。
- 長跑不動、不新增跑步日（不會把跑步排到週二／四／六重訓日；10/31 原本就有的跑步可加）、過去的日子不動（保留當時的調整）、
  10/19 週（半馬賽週）與 12/21 週（10K 測試週）不補；不在 WEEK_TOTAL 的週不補。跑超過不減量。
- 結果寫入 plan_adjust.json：{日期: {"km": 新公里, "from": 原公里, "week": 週一, "set": 設定日}}；make_plan.build() 讀檔套用並在 note 前加一句補量說明。
  今天以前的條目保留（歷史），今天起的條目每次重算。"""
import csv, json, os, datetime as dt, sys
from decimal import Decimal, ROUND_HALF_UP
HERE = os.path.dirname(os.path.abspath(__file__))
ADJ = os.path.join(HERE, "plan_adjust.json")
NO_MAKEUP = {"2026-10-19", "2026-12-21"}
CAP = Decimal("3.0")
HARD = ("長跑", "節奏", "間歇", "目標配速", "測試", "配速模擬")

def load():
    try: return json.load(open(ADJ))
    except FileNotFoundError: return {}

def strava_runs():
    out = {}
    for r in csv.DictReader(open(os.path.join(HERE, "activities.csv"))):
        out[r["date"]] = out.get(r["date"], Decimal(0)) + Decimal(r["km"])
    return out

def week_status(wk, today, days, runs):
    """回傳（實際 km, 剩餘跑步日 list）；days＝該週原計畫（未套用調整）。"""
    t = today.isoformat()
    end = (dt.date.fromisoformat(wk) + dt.timedelta(days=6)).isoformat()
    act = sum((v for d, v in runs.items() if wk <= d <= min(t, end)), Decimal(0))
    rem = [x for x in days if x["kind"] in ("run", "race") and (x["date"] > t or (x["date"] == t and t not in runs))]
    return act, rem

def compute(today=None):
    import make_plan
    today = today or dt.date.today(); t = today.isoformat()
    wk = make_plan.week_key(today).isoformat()
    adj = {d: v for d, v in load().items() if d < t}          # 過去的調整保留
    if wk in NO_MAKEUP or wk not in make_plan.WEEK_TOTAL:
        return adj, wk, None, Decimal(0)
    raw = [x for x in make_plan.build(apply_adjust=False, check_actual=False)["days"] if x["week"] == wk]
    # 已過去的日子若有調整，剩餘不受影響（剩餘只看今天起的原計畫）
    act, rem = week_status(wk, today, raw, strava_runs())
    gap = Decimal(str(make_plan.WEEK_TOTAL[wk])) - act - sum(Decimal(str(x["km"])) for x in rem)
    for x in rem:
        if gap <= 0: break
        if x["kind"] != "run" or any(h in x["type"] for h in HARD): continue
        add = min(gap, CAP).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP); gap -= add
        new = Decimal(str(x["km"])) + add
        adj[x["date"]] = dict(km=float(new), **{"from": x["km"]}, week=wk, set=t)
    return adj, wk, act, max(gap, Decimal(0))

def apply(today=None):
    adj, wk, act, short = compute(today)
    json.dump(adj, open(ADJ, "w"), ensure_ascii=False, indent=1, sort_keys=True)
    msg = f"動態補量：週起 {wk}" + (f"，已跑 {act} km" if act is not None else "（不補量的週）")
    msg += "；調整：" + ("、".join(f"{d} {v['from']:g}→{v['km']:g} km" for d, v in sorted(adj.items()) if v["week"] == wk) or "無")
    if short > 0: msg += f"；仍差 {short} km（剩餘輕鬆跑已到 +{CAP} km 上限或沒有可補的日子）"
    print(msg)
    return adj

if __name__ == "__main__":
    apply(dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)
