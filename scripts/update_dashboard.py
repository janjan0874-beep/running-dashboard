#!/usr/bin/env python3
"""由 /workspace/strava 的 CSV 重新計算並產生 running-dashboard 的資料檔。

用法:
  python3 update_dashboard.py            # 只重算 monthly.csv 並寫出 JSON/CSV 到 repo
  python3 update_dashboard.py --push     # 另外 git add/commit/push（觸發 GitHub Pages 更新）
流程詳見 UPDATE.md。僅使用標準函式庫。
"""
import csv, json, os, sys, subprocess, datetime as dt, collections, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "running-dashboard")
DATA = os.path.join(REPO, "data")
OUTLIER = None  # 於 main 設定

def to_sec(t):
    p = [int(x) for x in t.split(":")]
    return p[0]*3600+p[1]*60+p[2] if len(p) == 3 else p[0]*60+p[1]

def fmt_hms(s):
    s = int(round(s)); return f"{s//3600}:{s%3600//60:02d}:{s%60:02d}"

def fmt_pace(sec_per_km):
    if not sec_per_km: return ""
    s = int(round(sec_per_km)); return f"{s//60}:{s%60:02d}"

def pace_to_sec(p):
    if not p: return None
    m, s = p.split(":"); return int(m)*60+int(s)

def load_acts():
    rows = []
    for r in csv.DictReader(open(os.path.join(HERE, "activities.csv"))):
        km = float(r["km"]); sec = to_sec(r["moving"])
        ps = pace_to_sec(r["pace"]) or (sec/km if km else None)
        rows.append(dict(date=r["date"], km=km, sec=sec, pace_sec=ps))
    rows.sort(key=lambda x: x["date"])
    return rows

def recompute_monthly(acts):
    """舊月份（無活動明細）保留原值；有活動明細的月份以 activities.csv 重算。"""
    path = os.path.join(HERE, "monthly.csv")
    old = {r["month"]: r for r in csv.DictReader(open(path))}
    agg = collections.defaultdict(lambda: [0, 0.0, 0])
    for a in acts:
        k = a["date"][:7]; agg[k][0] += 1; agg[k][1] += a["km"]; agg[k][2] += a["sec"]
    for k, (n, km, sec) in agg.items():
        o = old.get(k)
        # 若與既有月統計一致（跑次與里程相同）就保留原值，避免四捨五入造成差異
        if o and int(o["runs"]) == n and abs(float(o["km"]) - km) < 0.005:
            continue
        old[k] = dict(month=k, runs=str(n), km=f"{km:.2f}", moving_time=fmt_hms(sec),
                      avg_pace=fmt_pace(sec/km) if km else "")
    # 補齊空月份
    ks = sorted(old); y, m = map(int, ks[0].split("-")); ey, em = map(int, ks[-1].split("-"))
    out = []
    while (y, m) <= (ey, em):
        k = f"{y}-{m:02d}"
        out.append(old.get(k, dict(month=k, runs="0", km="0", moving_time="0:00:00", avg_pace="")))
        m += 1
        if m == 13: y, m = y+1, 1
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["month", "runs", "km", "moving_time", "avg_pace"], lineterminator="\n")
        w.writeheader(); w.writerows(out)
    return out

def main():
    prof = json.load(open(os.path.join(HERE, "profile.json")))
    thr = prof["pace_outlier_threshold_min"]*60
    acts = load_acts()
    monthly = recompute_monthly(acts)
    last = dt.date.fromisoformat(acts[-1]["date"])
    os.makedirs(DATA, exist_ok=True)

    # ---- monthly.json
    mj = []
    for r in monthly:
        km = float(r["km"]); sec = to_sec(r["moving_time"]); ps = pace_to_sec(r["avg_pace"])
        mj.append(dict(month=r["month"], runs=int(r["runs"]), km=km, hours=round(sec/3600, 2),
                       time=r["moving_time"], pace=r["avg_pace"], pace_sec=ps,
                       outlier=bool(ps and ps > thr)))
    # ---- activities.json
    aj = [dict(date=a["date"], km=a["km"], time=fmt_hms(a["sec"]), pace=fmt_pace(a["pace_sec"]),
               pace_sec=round(a["pace_sec"]), outlier=bool(a["pace_sec"] > thr)) for a in acts]
    # ---- weekly（週一起算；跳過資料不完整的第一週）
    first = dt.date.fromisoformat(acts[0]["date"])
    wk0 = first - dt.timedelta(days=first.weekday())
    if first != wk0: wk0 += dt.timedelta(days=7)
    weekly = []
    w = wk0
    while w <= last:
        end = w + dt.timedelta(days=6)
        sel = [a for a in acts if w.isoformat() <= a["date"] <= end.isoformat()]
        t_end = min(end, last)
        s28 = start28 = t_end - dt.timedelta(days=27)
        roll = None
        if start28 >= first:
            roll = round(sum(a["km"] for a in acts if start28.isoformat() <= a["date"] <= t_end.isoformat())/4, 2)
        weekly.append(dict(week=w.isoformat(), km=round(sum(a["km"] for a in sel), 2), runs=len(sel),
                           partial=end > last, rolling4=roll))
        w += dt.timedelta(days=7)
    # ---- summary
    base = prof["alltime_baseline"]; asof = prof["as_of"]
    new = [a for a in acts if a["date"] > asof]
    at_runs = base["runs"]+len(new); at_km = base["km"]+sum(a["km"] for a in new)
    at_sec = base["seconds"]+sum(a["sec"] for a in new)
    def window(days, end=last):
        s = end - dt.timedelta(days=days-1)
        return [a for a in acts if s.isoformat() <= a["date"] <= end.isoformat()]
    w12 = window(84); w4 = window(28)
    longest = max(acts, key=lambda a: a["km"])
    mmap = {m["month"]: m for m in mj}
    def sum_months(n, shift=0):
        ks = [m["month"] for m in mj]
        sel = ks[len(ks)-n-shift: len(ks)-shift] if shift else ks[-n:]
        return round(sum(mmap[k]["km"] for k in sel), 1)
    sep, aug = mmap.get("2026-09"), mmap.get("2026-08")
    jump = round((sep["km"]/aug["km"]-1)*100) if sep and aug and aug["km"] else None
    ok = [m for m in mj if not m["outlier"] and m["km"] > 0]
    summary = dict(
        generated=dt.date.today().isoformat(), data_through=last.isoformat(),
        race_date=prof["race_date"], first_run=prof["first_run"], prs=prof["prs"],
        alltime=dict(runs=at_runs, km=round(at_km, 1), time=fmt_hms(at_sec), pace=prof["alltime_avg_pace"]),
        w12=dict(runs=len(w12), km=round(sum(a["km"] for a in w12), 2),
                 km_per_week=round(sum(a["km"] for a in w12)/13, 1),  # Strava「近12週」涵蓋 13 個日曆週，口徑與 Strava 相同
                 pace=fmt_pace(sum(a["sec"] for a in w12)/sum(a["km"] for a in w12))),
        w4=dict(runs=len(w4), km=round(sum(a["km"] for a in w4), 1), km_per_week=round(sum(a["km"] for a in w4)/4, 1)),
        longest=dict(km=longest["km"], date=longest["date"]),
        best_month=max(mj, key=lambda m: m["km"])["month"],
        trend=dict(m3=sum_months(3), m3_prev=sum_months(3, 3), m6=sum_months(6), m6_prev=sum_months(6, 6),
                   m12=sum_months(12), m12_prev=round(sum(m["km"] for m in mj[:-12]), 1) if len(mj) > 12 else None,
                   aug_to_sep_pct=jump, sep_km=sep["km"] if sep else None, aug_km=aug["km"] if aug else None),
        outlier_threshold=prof["pace_outlier_threshold_min"],
    )
    for name, obj in [("monthly", mj), ("activities", aj), ("weekly", weekly), ("summary", summary)]:
        json.dump(obj, open(os.path.join(DATA, name+".json"), "w"), ensure_ascii=False, indent=1)
    for f in ("monthly.csv", "activities.csv"):
        open(os.path.join(DATA, f), "w").write(open(os.path.join(HERE, f)).read())
    # 計畫
    sys.path.insert(0, HERE)
    import make_plan
    p = make_plan.build()
    json.dump(p, open(os.path.join(DATA, "plan.json"), "w"), ensure_ascii=False, indent=1)
    md = make_plan.to_md(p)
    open(os.path.join(HERE, "plan.md"), "w").write(md); open(os.path.join(REPO, "plan.md"), "w").write(md)
    # 備份腳本到 repo
    os.makedirs(os.path.join(REPO, "scripts"), exist_ok=True)
    for f in ("update_dashboard.py", "make_plan.py", "profile.json", "UPDATE.md"):
        src = os.path.join(HERE, f)
        if os.path.exists(src): open(os.path.join(REPO, "scripts", f), "w").write(open(src).read())
    print("資料已更新，資料截至", last, "；更新日", summary["generated"])
    if "--push" in sys.argv:
        run = lambda *c: subprocess.run(c, cwd=REPO, check=True)
        run("git", "add", "-A")
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO).returncode:
            run("git", "commit", "-m", f"更新跑步資料 {summary['generated']}")
            run("git", "push", "origin", "main")
        else:
            print("無變更，略過 commit")

if __name__ == "__main__":
    main()
