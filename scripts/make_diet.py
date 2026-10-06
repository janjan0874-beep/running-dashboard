#!/usr/bin/env python3
"""每日飲食計畫：讀 make_plan.py 的逐日訓練，產生 data/diet.json（以日期為鍵）。
update_dashboard.py 每次執行都會呼叫 build()，所以課表改了，飲食會自動跟著改。
所有克數以 0.1 g 為單位計算（內部用「十分之一克」整數，避免浮點誤差），熱量一律 4/4/9。"""
import json, os, re, datetime as dt
import make_plan

# ---- 使用者資料：profile.json 的 body（2026-10-06：176 cm、32 歲、男、71 kg、體脂 17.5%）
_B = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile.json")))["body"]
WEIGHT = float(_B["weight_kg"]); HEIGHT = float(_B["height_cm"]); AGE = int(_B["age"]); SEX = _B["sex"]
BODY_FAT = float(_B["body_fat_pct"]); BODY_FAT_GOAL = float(_B["body_fat_goal_pct"])
DEFICIT = 183          # kcal/天：10/6–10/25 一般日、12/27 10K 測試日的缺口
# 12/31 前減脂目標：2.09 kg × 7700 kcal＝16093 kcal（10/6–12/31 合計）。10/26 起的一般日用同一個缺口 D，
# 由 build() 依其他日子的實際缺口自動反推（課表一改，每日 8:00 重建時 D 會自動重算），D 上限 400。
FAT_LOSS_KG, KCAL_PER_KG = 2.09, 7700
GOAL_T = int(FAT_LOSS_KG * KCAL_PER_KG * 10 + 0.5)       # 160930（十分之一 kcal）
D_START, D_CAP = "2026-10-26", 400.0
# 特殊日（2026-10-06 使用者決定）：
#  10/23、10/24 肝醣超補：目標＝碳水 568 g＋當天蛋白質＋脂肪 40 g（計畫性盈餘，不設缺口）
#  10/25 比賽日：目標＝碳水 355 g＋蛋白質＋脂肪 57 g（不設缺口、不設上限）
#  14 km 以上長跑的前一天：碳水 355 g、脂肪 42.6 g，缺口＝實際結果
FAT_LOAD, FAT_RACE = 40.0, 57.0
# Mifflin-St Jeor（1990）：男 10W + 6.25H − 5A + 5；女 −161
BMR = 10 * WEIGHT + 6.25 * HEIGHT - 5 * AGE + (5 if SEX == "male" else -161)
ACTIVITY = float(_B.get("activity_factor", 1.2))   # 日常活動係數（運動另外加）；2026-10-06 依 Pixel Watch 校正為 1.3（profile.json）
RUN_KCAL_PER_KG_KM = 1.0           # 跑步淨消耗 1 kcal/kg/km
MET_STRENGTH, MET_HYROX = 5.0, 8.0 # Compendium of Physical Activities
STR_MIN_DEFAULT = 45
FAT_FLOOR = 0.6                    # g/kg
FAT_CAP = 1.0                      # g/kg；目標熱量放得下更多時，多的放進碳水
START, END = "2026-10-06", "2026-12-31"
WD = "一二三四五六日"

# ---- 食物營養（每單位；十分之一克）。USDA FoodData Central（SR Legacy）＋瓶身標示
F = {
 "rice":    dict(name="白飯（熟）", unit="100 g", c=282, p=27,  f=3,  src="USDA FDC 168878 Rice, white, long-grain, enriched, cooked：碳水 28.2 g、蛋白質 2.7 g、脂肪 0.3 g／100 g"),
 "pasta":   dict(name="義大利麵（熟）", unit="100 g", c=309, p=58, f=9, src="USDA SR 20121 Spaghetti, cooked, enriched, without added salt：碳水 30.9 g、蛋白質 5.8 g、脂肪 0.9 g／100 g"),
 "sweetpotato": dict(name="瓜瓜園地瓜（冰烤地瓜）", unit="100 g", c=359, p=11, f=2, src="瓜瓜園冰烤地瓜包裝營養標示（每 100 g）：碳水 35.9 g、蛋白質 1.1 g、脂肪 0.2 g（Pure17Go 350 g 盒裝與優統食品 1 kg 包裝的轉載標示相同）；熱量依 4/4/9 計算。"),
 "banana":  dict(name="香蕉（中型 118 g）", unit="根", c=270, p=13, f=4, src="USDA FDC 173944 Bananas, raw，中型 118 g：碳水 27.0 g、蛋白質 1.3 g、脂肪 0.4 g"),
 "egg":     dict(name="雞蛋（大顆 50 g，水煮）", unit="顆", c=6, p=63, f=53, src="USDA FDC 173424 Egg, whole, cooked, hard-boiled，大顆 50 g：蛋白質 6.3 g、脂肪 5.3 g、碳水 0.6 g"),
 "chicken": dict(name="雞胸肉（熟重，巴掌大）", unit="100 g", c=0, p=310, f=36, src="USDA FDC 171477 Chicken breast, meat only, cooked, roasted：蛋白質 31.0 g、脂肪 3.6 g、碳水 0 g／100 g"),
 "meiji":   dict(name="Meiji High Protein（350 ml）", unit="瓶", c=98, p=300, f=21, src="Meiji High Protein 350 ml：蛋白質 30.0 g（依你提供）；碳水 9.8 g、脂肪 2.1 g（巧克力口味瓶身標示；香蕉、綠茶口味碳水 8.1 g）"),
 "powder":  dict(name="蛋白粉", unit="份", c=0, p=350, f=0, src="蛋白粉 1 份：蛋白質 35.0 g（依你提供）；品牌未知，碳水與脂肪未計入"),
}
SP_G = {"rest": 100, "str": 100, "easy": 120, "long": 150, "quality": 150, "prelong": 150, "race": 150, "load": 180}   # 早餐地瓜克數
CARB_GKG = {"rest": 3, "str": 3, "easy": 4, "long": 5, "quality": 5, "prelong": 5, "race": 5, "load": 8}
TIER_LABEL = {"rest": "休息日", "str": "肌力日", "easy": "輕鬆跑日", "long": "長跑日", "quality": "強度課日",
              "prelong": "長跑前一天", "race": "比賽日", "load": "肝醣超補日"}
LOAD_DAYS = {"2026-10-23", "2026-10-24"}
HALF_RACE = "2026-10-25"
RACE_BREAKFAST_C = 1420   # 142 g（2 g/kg），起跑前 3 小時

def hu(x):  # 四捨五入到整數（十分之一克）
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)

UNIT_WORD = {"powder": "份", "egg": "顆", "banana": "根", "meiji": "瓶"}

def item(key, qty, when=""):
    """qty：份數；單位為 100 g 的食物 qty＝克數/100。回傳十分之一克。"""
    fd = F[key]
    if fd["unit"] == "100 g":
        g = qty; q = g / 100; amount = f"{g} g"
    else:
        q = qty; amount = f"{qty} {UNIT_WORD[key]}"
    return dict(key=key, name=fd["name"], when=when, amount=amount, c=hu(fd["c"]*q), p=hu(fd["p"]*q), f=hu(fd["f"]*q))

def g1(t):   # 十分之一克 → "12.3"
    return f"{t/10:.1f}"

def kcal_t(c, p, f):  # 十分之一克 → 十分之一 kcal
    return 4*c + 4*p + 9*f

def sums(items):
    c = sum(i["c"] for i in items); p = sum(i["p"] for i in items); f = sum(i["f"] for i in items)
    return c, p, f

def round10(x):
    return int(x/10 + 0.5) * 10

def classify(entries, tomorrow):
    d = entries[0]["date"]
    if d in LOAD_DAYS: return "load"
    if any(e["kind"] == "race" for e in entries): return "race"
    runs = [e for e in entries if e["kind"] == "run"]
    if any("長跑" in e["type"] and e["km"] >= 10 for e in runs): return "long"   # 10 km 以下的輕鬆長跑用 4 g/kg
    if any(k in e["type"] for e in runs for k in ("節奏", "間歇", "目標配速", "測試", "配速模擬")): return "quality"
    if any(e["kind"] == "run" and e["km"] >= 14 for e in tomorrow): return "prelong"
    if runs: return "easy"
    if any(e["kind"] == "str" for e in entries): return "str"
    return "rest"

def exercise(ents):
    """回傳（運動消耗，十分之一 kcal；明細文字 list）。"""
    tot, parts = 0, []
    for e in ents:
        if e["kind"] in ("run", "race"):
            k = hu(RUN_KCAL_PER_KG_KM * WEIGHT * e["km"] * 10); tot += k
            parts.append(f"跑步 {e['km']:g} km × {RUN_KCAL_PER_KG_KM * WEIGHT:g} = {g1(k)}")
        elif e["kind"] == "str" or "Hyrox" in e["type"] or "HIIT" in e["type"]:
            met = MET_HYROX if ("Hyrox" in e["type"] or "HIIT" in e["type"]) else MET_STRENGTH
            m = re.search(r"(\d+)\s*分鐘", e["note"]); mins = int(m.group(1)) if m else STR_MIN_DEFAULT
            k = hu((met - 1) * WEIGHT * mins / 60 * 10); tot += k
            nm = "Hyrox／HIIT" if met == MET_HYROX else "肌力"
            parts.append(f"{nm} {mins} 分鐘：（MET {met:.1f} − 1）× {WEIGHT:g} × {mins}／60 = {g1(k)}")
    return tot, parts

def build():
    """兩段式：先用 183 算出 D 以外的日子的缺口，再反推 10/26 起一般日的統一缺口 D，重算一次。"""
    first = _build(DEFICIT * 10)
    days = first["days"]
    flex = [k for k, x in days.items() if x["energy"]["flex"]]
    fixed_gap = sum(x["energy"]["gap_t"] for k, x in days.items() if k not in flex)
    need = GOAL_T - fixed_gap
    d_t = int(need / len(flex) + 0.5) if flex else 0
    capped = d_t > hu(D_CAP * 10)
    if capped: d_t = hu(D_CAP * 10)
    p = _build(d_t)
    total = sum(x["energy"]["gap_t"] for x in p["days"].values())
    pre = sum(x["energy"]["gap_t"] for k, x in p["days"].items() if k <= "2026-10-25")
    assert all(p["days"][k]["energy"]["gap_t"] == d_t for k in flex)
    short = GOAL_T - total
    p["meta"]["goal"] = dict(goal=g1(GOAL_T), total=g1(total), through_1025=g1(pre), d=g1(d_t), flex_days=len(flex),
                             fixed_gap=g1(fixed_gap), capped=capped, shortfall=g1(short) if capped else "0.0",
                             text=f"12/31 前總熱量缺口目標 {g1(GOAL_T).replace('.0', '')} kcal（{FAT_LOSS_KG:g} kg 脂肪 × {KCAL_PER_KG}），目前計畫合計 {g1(total)} kcal"
                                  + (f"；10/26 起一般日每天缺口 {g1(d_t)} kcal" if not capped else f"；每天缺口已到上限 {D_CAP:g} kcal，仍差 {g1(short)} kcal"))
    return p

def _build(late_def_t):
    plan = make_plan.build()
    byd = {}
    for e in plan["days"]:
        byd.setdefault(e["date"], []).append(e)
    out = {}
    BMR_T = hu(BMR * 10); BASE_T = hu(BMR * ACTIVITY * 10); FLOOR_T = hu(FAT_FLOOR * WEIGHT * 10); CAP_T = hu(FAT_CAP * WEIGHT * 10)
    d = dt.date.fromisoformat(START)
    while d.isoformat() <= END:
        ds = d.isoformat(); ents = byd.get(ds, [])
        if not ents:
            d += dt.timedelta(days=1); continue
        tmr = byd.get((d + dt.timedelta(days=1)).isoformat(), [])
        tier = classify(ents, tmr)
        runs = [e for e in ents if e["kind"] in ("run", "race")]; strs = [e for e in ents if e["kind"] == "str"]
        has_run, has_str = bool(runs), bool(strs)
        # ---- 熱量：TDEE＝BMR × ACTIVITY（1.3）＋運動
        EX_T, ex_parts = exercise(ents)
        TDEE_T = BASE_T + EX_T
        C_TIER = hu(CARB_GKG[tier] * WEIGHT * 10)
        # ---- 固定餐點
        meals = []
        if ds == HALF_RACE:
            base = [item("powder", 1), item("egg", 2), item("banana", 2)]
            bc = sum(i["c"] for i in base)
            rice_g = hu((RACE_BREAKFAST_C - bc) / F["rice"]["c"] * 100)
            meals.append(dict(slot="早餐（起跑前 3 小時）", items=base + [item("rice", rice_g)],
                              tips=[f"早餐碳水 {g1(RACE_BREAKFAST_C)} g（2 g/kg）；只吃平常吃過、低纖維的食物。"]))
            meals.append(dict(slot="比賽中", items=[], text_items=["能量膠 × 2（10 km、16 km 各 1 包，配水）"],
                              tips=["能量膠沒有指定品牌，碳水未計入今日總量；用 10/11、10/18 演練過的同一款。"]))
        else:
            meals.append(dict(slot="早餐", items=[item("powder", 1), item("egg", 2), item("sweetpotato", SP_G[tier])], tips=[]))
        tr_items = []
        if ds == HALF_RACE:
            tr_items.append(item("meiji", 1, "賽後 30 分鐘內")); slot_tr = "賽後"
        elif has_run or has_str:
            if has_run: tr_items.append(item("banana", 1, "跑前 45 分鐘"))
            if has_run and has_str:
                tr_items.append(item("meiji", 1, "跑後 30 分鐘內")); tr_items.append(item("meiji", 1, "肌力後 30 分鐘內"))
            else:
                tr_items.append(item("meiji", 1, "訓練後 30 分鐘內"))
            slot_tr = "訓練前後"
        else:
            tr_items.append(item("meiji", 1, "下午點心")); slot_tr = "下午點心"
        late = [item("meiji", 1, "睡前")] if sum(1 for i in tr_items if i["key"] == "meiji") < 2 else []
        snack_fixed = [item("banana", 2)] if tier == "load" else []
        lunch_fixed = [item("chicken", 100, "放進麻辣燙")]
        fixed = [i for m in meals for i in m["items"]] + tr_items + late + snack_fixed + lunch_fixed
        fc, fp, ff = sums(fixed)
        parts = 3 if tier == "load" else 2
        rice0 = round10((C_TIER - fc) / parts / F["rice"]["c"] * 100)   # 依碳水分級的午餐（與加餐）白飯
        ex_key = "rice" if tier in ("rest", "str") else "pasta"
        def ex_for(dc):
            return item(ex_key, max(0, hu(dc / F[ex_key]["c"] * 100)))
        def rice_items(lr, sr):
            return [item("rice", lr)] + ([item("rice", sr)] if tier == "load" else [])
        # ---- 解
        lr = sr = rice0
        rc, rp, rf = sums(rice_items(lr, sr))
        pk = 0; mode = "normal"; adj = None; flex = False; day_def = 0
        def solve_fixed(Ff, lr, low):
            """脂肪固定在 Ff（下限或上限），晚餐碳水補到剛好；晚餐與午餐白飯碳水差超過 30 g 時以 10 g 白飯調整午餐。"""
            for guard in range(300):
                rc, rp, _ = sums(rice_items(lr, lr))
                ep = 0
                for _ in range(5):
                    dc = (TK - 9 * Ff - 4 * (fc + rc) - 4 * (fp + rp + ep)) // 4
                    ep = ex_for(max(dc, 0))["p"]
                lc = item("rice", lr)["c"]
                if (dc < 0 or dc < lc - 300) and lr >= 10: lr -= 10; continue
                if dc > lc + 300: lr += 10; continue
                break
            rem = TK - 4 * (fc + rc + dc) - 4 * (fp + rp + ep)
            rng = range(Ff, Ff + 4) if low else range(Ff - 3, Ff + 1)
            ok = [f for f in rng if (rem - 9 * f) % 4 == 0]
            F_ = min(ok) if low else max(ok)
            dc += (rem - 9 * F_) // 4           # 0.1 kcal 尾數由晚餐碳水吸收
            return lr, rc, rp, dc, ep, F_
        if tier == "load" or ds == HALF_RACE or tier == "prelong":
            mode = "load" if tier == "load" else ("race" if ds == HALF_RACE else "prelong")
            FAT_T = {"load": hu(FAT_LOAD * 10), "race": hu(FAT_RACE * 10), "prelong": FLOOR_T}[mode]
            dc = C_TIER - fc - rc
            ep = ex_for(dc)["p"]
            TK = 4 * C_TIER + 4 * (fp + rp + ep) + 9 * FAT_T
        else:
            flex = ds >= D_START and not (tier == "race")          # 12/27 10K 測試日維持 183
            day_def = late_def_t if flex else DEFICIT * 10
            TK = TDEE_T - day_def
            dc = C_TIER - fc - rc
            ep = ex_for(dc)["p"]
            rem = TK - 4 * C_TIER - 4 * (fp + rp + ep)
            cands = [f for f in range(rem // 9 - 4, rem // 9 + 5) if (rem - 9 * f) % 4 == 0]
            FAT_T = min(cands, key=lambda f: abs(rem - 9 * f))
            pk = (rem - 9 * FAT_T) // 4          # 0.1 g 等級的熱量尾數，由晚餐蛋白質預算吸收
            if FAT_T < FLOOR_T:
                adj = "floor"; pk = 0
                lr, rc, rp, dc, ep, FAT_T = solve_fixed(FLOOR_T, lr, True)
            elif FAT_T > CAP_T:
                adj = "cap"; pk = 0
                lr, rc, rp, dc, ep, FAT_T = solve_fixed(CAP_T, lr, False)
        sr = lr if tier != "load" else rice0
        assert dc >= 0, (ds, dc)
        C = fc + rc + dc
        lunch = lunch_fixed + [item("rice", lr)]
        meals.append(dict(slot="午餐", title="麻辣燙（不加辣）配白飯", items=lunch,
                          tips=["雞胸肉 100 g（或等量瘦肉：里肌、魚片、蝦）和青菜放進麻辣燙。",
                                "炸物（豆皮、炸豆包、油條）與加工丸子、餃類少拿。",
                                "湯不要喝（湯裡有油）。"]))
        if tier == "load":
            meals.append(dict(slot="加餐（下午）", items=snack_fixed + [item("rice", sr)], tips=["肝醣超補：碳水分散到多餐，選低纖維食物。"]))
        meals.append(dict(slot=slot_tr, items=tr_items, tips=(["訓練前後依實際訓練時間調整；香蕉在跑前 45 分鐘吃。"] if has_run and ds != HALF_RACE else [])))
        if late:
            meals.append(dict(slot="睡前", items=late, tips=[]))
        # ---- 晚餐（自由）：剩餘預算
        used = [i for m in meals for i in m["items"]]
        uc, up, uf = sums(used)
        ex = ex_for(dc)
        dp = ep + pk
        dfat = FAT_T - uf
        P = up + dp
        assert uc + dc == C and 4 * C + 4 * P + 9 * FAT_T == TK, (ds, 4 * C + 4 * P + 9 * FAT_T, TK)
        assert dc >= 0 and dfat >= 0 and dp >= 0, (ds, dc, dfat, dp)
        other_fat = max(0, dfat - ex["f"])
        dinner = dict(carbs=g1(dc), protein=g1(dp), fat=g1(dfat), kcal=g1(kcal_t(dc, dp, dfat)),
                      example=dict(food=ex["name"], grams=int(ex["amount"].split()[0]), carbs=g1(ex["c"]), protein=g1(ex["p"]), fat=g1(ex["f"]),
                                   other_fat=g1(other_fat),
                                   text=f"{ex['name'].replace('（熟）','')} {ex['amount']}（碳水 {g1(ex['c'])} g、蛋白質 {g1(ex['p'])} g、脂肪 {g1(ex['f'])} g）＋青菜＋烹調油／醬汁／配料脂肪 {g1(other_fat)} g"),
                      tips=["晚餐自由選，控制在上面的剩餘預算內。",
                            "蛋白質已由早餐、午餐與 2 瓶 Meiji 吃夠；晚餐加肉、魚或豆腐，請從脂肪預算扣。"])
        def fmt_items(items):
            return [dict(name=i["name"], when=i["when"], amount=i["amount"], na=(["carbs", "fat"] if i["key"] == "powder" else []), carbs=g1(i["c"]), protein=g1(i["p"]), fat=g1(i["f"]),
                         kcal=g1(kcal_t(i["c"], i["p"], i["f"]))) for i in items]
        mo = []
        for m in meals:
            c, p, f = sums(m["items"])
            mo.append(dict(slot=m["slot"], title=m.get("title", ""), items=fmt_items(m["items"]), text_items=m.get("text_items", []),
                           subtotal=dict(carbs=g1(c), protein=g1(p), fat=g1(f), kcal=g1(kcal_t(c, p, f))), tips=m["tips"]))
        train = "＋".join((f"跑步 {e['km']:g} km（{e['type']}）" if e["kind"] in ("run", "race") else
                          ("肌力（" + e["type"] + "）" if e["kind"] == "str" else e["type"])) for e in ents)
        notes = []
        GAP = TDEE_T - TK
        if mode == "load":
            notes.append("賽前補碳，當天不設熱量缺口。")
        elif mode == "race":
            notes.append("比賽日不設熱量缺口。")
        elif mode == "prelong":
            notes.append(f"長跑前一天：碳水維持 {g1(C_TIER)} g、脂肪 {g1(FLOOR_T)} g，" + (f"當天缺口 {g1(GAP)} kcal。" if GAP >= 0 else f"當天沒有缺口，比消耗多 {g1(-GAP)} kcal。"))
        if adj == "floor":
            ch = ([f"午餐白飯 {rice0} g → {lr} g"] if lr != rice0 else []) + [f"晚餐碳水預算 {g1(dc)} g"]
            notes.append(f"今天目標熱量放不下碳水 {CARB_GKG[tier]} g/kg（{g1(C_TIER)} g）：脂肪已降到下限 {g1(FLOOR_T)} g（{FAT_FLOOR:.1f} g/kg），碳水減為 {g1(C)} g（" + "、".join(ch) + "）。")
        if adj == "cap":
            ch = ([f"午餐白飯 {rice0} g → {lr} g"] if lr != rice0 else []) + [f"晚餐碳水預算 {g1(dc)} g"]
            notes.append(f"脂肪已到上限 {g1(CAP_T)} g（{FAT_CAP:.1f} g/kg），多出的熱量放進碳水：碳水增為 {g1(C)} g（" + "、".join(ch) + "）。")
        if d.weekday() == 6:
            notes.append("週日：早上起床、如廁後空腹量體重、體脂、腰圍，記錄後回報。")
        if tier == "prelong":
            notes.append("明天長跑：晚餐以白飯或義大利麵為主，少油、少纖維。")
        if tier == "load":
            notes.append("肝醣超補（10/23、10/24）：少油、少纖維，多喝水。")
        if mode == "normal": tt = f"目標 {g1(TK)} kcal（−{g1(day_def).replace('.0', '') if day_def % 10 == 0 else g1(day_def)}）"
        elif GAP >= 0: tt = f"目標 {g1(TK)} kcal（缺口 {g1(GAP)} kcal）"
        else: tt = f"目標 {g1(TK)} kcal（盈餘 {g1(-GAP)} kcal）"
        energy = dict(bmr=g1(BMR_T), base=g1(BASE_T), exercise=g1(EX_T), exercise_parts=ex_parts, tdee=g1(TDEE_T),
                      target=g1(TK), gap=g1(GAP), gap_t=GAP, mode=mode, fat_adjust=adj or "", flex=flex,
                      burn_text=f"消耗 {g1(TDEE_T)} kcal（基礎代謝 {BMR:g} × {ACTIVITY:g} ＋ 運動 {g1(EX_T)}）",
                      target_text=tt)
        day = dict(date=ds, weekday="週" + WD[d.weekday()], week=ents[0]["week"], tier=tier,
                   tier_label=f"{TIER_LABEL[tier]}｜碳水 {CARB_GKG[tier]} g/kg", training=train, energy=energy,
                   targets=dict(carbs=g1(C), protein=g1(P), fat=g1(FAT_T), kcal=g1(TK),
                                protein_note=f"固定 138.6 g＋主食、地瓜與香蕉 {g1(P - 1386)} g",
                                carbs_gkg=f"{C/10/WEIGHT:.2f}", protein_gkg=f"{P/10/WEIGHT:.2f}", fat_gkg=f"{FAT_T/10/WEIGHT:.2f}",
                                carbs_reduced=adj == "floor", carbs_raised=adj == "cap"),
                   meals=mo, dinner=dinner, notes=notes, sunday=d.weekday() == 6)
        def short(m):
            parts_ = [f"{i['name'].split('（')[0]} {i['amount']}" + (f"（{i['when']}）" if i["when"] and i["when"] != m["slot"] else "") for i in m["items"]] + m.get("text_items", [])
            return f"{m['slot']}：" + (m["title"] + "（" if m["title"] else "") + "、".join(parts_) + ("）" if m["title"] else "")
        day["text"] = (f"{ds[5:].replace('-', '/')}（{day['weekday']}）飲食｜{day['tier_label']}｜{energy['burn_text']}；{energy['target_text']}｜今日：碳水 {g1(C)} g、蛋白質 {g1(P)} g、脂肪 {g1(FAT_T)} g。"
                       + "；".join([short(m) for m in mo if m["slot"] != "睡前"]
                                   + [f"晚餐（自由）剩餘：碳水 {dinner['carbs']} g、蛋白質 {dinner['protein']} g、脂肪 {dinner['fat']} g、{dinner['kcal']} kcal（例：{dinner['example']['text']}）"]
                                   + [short(m) for m in mo if m["slot"] == "睡前"]) + "。"
                       + "".join(notes))
        out[ds] = day
        d += dt.timedelta(days=1)
    weeks = {}
    for x in out.values():
        w = weeks.setdefault(x["week"], dict(gap_t=0, days=0, first=x["date"]))
        w["gap_t"] += x["energy"]["gap_t"]; w["days"] += 1
    week_gap = {k: dict(gap=g1(v["gap_t"]), days=v["days"], first=v["first"],
                        text=(f"本週熱量缺口合計 {g1(v['gap_t'])} kcal" if v["gap_t"] >= 0 else f"本週熱量缺口合計 −{g1(-v['gap_t'])} kcal（本週為盈餘）") + (f"（{v['first'][5:].replace('-', '/')} 起 {v['days']} 天）" if v["days"] < 7 else ""))
                for k, v in weeks.items()}
    meta = dict(
        weeks=week_gap, weight=WEIGHT, height=HEIGHT, age=AGE, sex=SEX, body_fat=BODY_FAT, body_fat_goal=BODY_FAT_GOAL, deficit=DEFICIT, bmr=g1(BMR_T), start=START, end=END,
        summary=f"176 cm、32 歲、男、{WEIGHT:g} kg、體脂 {BODY_FAT:g}%，目標 12/31 前體脂 {BODY_FAT_GOAL:g}%。基礎代謝 {BMR:g} kcal；每日消耗＝{BMR:g} × {ACTIVITY:g}＋當天課表運動；目標＝消耗 − 缺口（10/6–10/25 一般日 {DEFICIT} kcal；10/26 起一般日 {g1(late_def_t)} kcal；特殊日見下）。",
        rules=[f"基礎代謝（Mifflin-St Jeor，男）：10 × {WEIGHT:g} ＋ 6.25 × {HEIGHT:g} − 5 × {AGE} ＋ 5 ＝ {BMR:g} kcal；× {ACTIVITY:g}（日常活動）＝ {g1(BASE_T)} kcal。",
               f"運動消耗：跑步 {RUN_KCAL_PER_KG_KM * WEIGHT:g} kcal／km（1.0 kcal/kg/km）× 課表公里；肌力（MET {MET_STRENGTH:.1f} − 1）× {WEIGHT:g} × 小時（課表沒寫時間就算 {STR_MIN_DEFAULT} 分鐘）；Hyrox／HIIT 用 MET {MET_HYROX:.1f}；休息日 0。",
               f"每日目標＝消耗 − 缺口：10/6–10/25 的一般日 {DEFICIT} kcal；10/26 起的一般日統一 {g1(late_def_t)} kcal，由 12/31 前總缺口目標 16093 kcal（{FAT_LOSS_KG:g} kg 脂肪 × {KCAL_PER_KG}）扣掉其他日子的實際缺口後平均分配（上限 {D_CAP:g} kcal）；12/27 10K 測試日 {DEFICIT} kcal。特殊日：10/23、10/24 賽前補碳＝碳水 568 g＋蛋白質＋脂肪 {FAT_LOAD:g} g（不設缺口）；10/25 比賽日＝碳水 355 g＋蛋白質＋脂肪 {FAT_RACE:g} g（不設缺口）；14 km 以上長跑的前一天＝碳水 355 g＋蛋白質＋脂肪 {g1(hu(FAT_FLOOR * WEIGHT * 10))} g，缺口為實際結果。週標題顯示本週缺口合計（每日消耗 − 目標）。",
               "碳水：休息日與肌力日 3 g/kg（213 g）；輕鬆跑／恢復跑日（含 10 km 以下的輕鬆長跑）4 g/kg（284 g）；10 km 以上長跑日、強度課日、10K 測試日、半馬日與 14 km 以上長跑的前一天 5 g/kg（355 g）；10/23、10/24 肝醣超補 8 g/kg（568 g）。",
               "蛋白質：固定 138.6 g＝Meiji 30 g × 2 瓶（60.0）＋蛋白粉 1 份（35.0）＋雞蛋 × 2（12.6）＋雞胸肉 100 g（31.0），再加上白飯、義大利麵、地瓜、香蕉的蛋白質。",
               f"脂肪：補到碳水 × 4＋蛋白質 × 4＋脂肪 × 9 剛好等於目標熱量；下限 {FAT_FLOOR:.1f} g/kg（{g1(FLOOR_T)} g）、上限 {FAT_CAP:.1f} g/kg（{g1(CAP_T)} g）。低於下限時改減碳水，高於上限時多的熱量放進碳水（晚餐與午餐白飯），卡片上會註明。"],
        footnotes=[
            "基礎代謝：Mifflin MD, St Jeor ST, et al. A new predictive equation for resting energy expenditure in healthy individuals. Am J Clin Nutr 1990;51:241–247。",
            "運動 MET：Compendium of Physical Activities（Ainsworth BE et al. 2011；Herrmann SD et al. 2024 成人版）；肌力 MET 5.0、Hyrox／HIIT MET 8.0，淨消耗＝（MET − 1）× 體重 × 小時。",
            "跑步淨消耗 1 kcal/kg/km：跑步每公里的淨能量消耗與速度大致無關，約等於體重（kg）kcal（Margaria et al. 1963；ACSM Guidelines 跑步代謝公式）。",
            "每公斤體重的碳水、蛋白質、脂肪建議依據：ACSM／美國營養與飲食學會／加拿大營養師協會 2016 聯合立場聲明（Thomas et al., Med Sci Sports Exerc 48:543）與 ISSN 立場聲明（Jäger et al. 2017 蛋白質與運動；Kerksick et al. 2017 營養時機）。",
            "麻辣燙的湯、油與青菜沒有計入（份量與用油每家不同），請不要喝湯；表中只計白飯、雞胸肉等有明確數值的食物。",
            "蛋白粉品牌未知，只計蛋白質 35.0 g；能量膠品牌未知，碳水未計入。Meiji 碳水與脂肪以巧克力口味瓶身標示計。",
            "消耗是公式估算值，請以每週日的體重、體脂、腰圍趨勢檢查：連續 2 週體重沒有下降就再調整。",
            f"活動係數 {ACTIVITY:g} 依 Pixel Watch 9/7–10/4 平均消耗 {_B['watch_calibration']['avg_4wk']} kcal／天校正（手錶會高估，未完全採用）。" if _B.get("watch_calibration") else "",
        ] + ["食物數值：" + F[k]["src"] for k in ("rice", "pasta", "sweetpotato", "banana", "egg", "chicken", "meiji", "powder")],
    )
    return dict(meta=meta, days=out)

if __name__ == "__main__":
    import sys, os
    p = build()
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    json.dump(p, open(os.path.join(out, "data/diet.json"), "w"), ensure_ascii=False, indent=1)
