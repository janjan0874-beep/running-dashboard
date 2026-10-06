#!/usr/bin/env python3
"""每日飲食計畫：讀 make_plan.py 的逐日訓練，產生 data/diet.json（以日期為鍵）。
update_dashboard.py 每次執行都會呼叫 build()，所以課表改了，飲食會自動跟著改。
所有克數以 0.1 g 為單位計算（內部用「十分之一克」整數，避免浮點誤差），熱量一律 4/4/9。"""
import json, datetime as dt
import make_plan

# ---- 使用者資料（2026-10-06 提供）
WEIGHT = 71.0          # kg
BODY_FAT = 17.5        # %
BODY_FAT_GOAL = 15.0   # %，12/31 前
DEFICIT = 183          # kcal/天（目標赤字）
START, END = "2026-10-06", "2026-12-31"
WD = "一二三四五六日"

# ---- 食物營養（每單位；十分之一克）。USDA FoodData Central（SR Legacy）＋瓶身標示
F = {
 "rice":    dict(name="白飯（熟）", unit="100 g", c=282, p=27,  f=3,  src="USDA FDC 168878 Rice, white, long-grain, enriched, cooked：碳水 28.2 g、蛋白質 2.7 g、脂肪 0.3 g／100 g"),
 "pasta":   dict(name="義大利麵（熟）", unit="100 g", c=309, p=58, f=9, src="USDA SR 20121 Spaghetti, cooked, enriched, without added salt：碳水 30.9 g、蛋白質 5.8 g、脂肪 0.9 g／100 g"),
 "oats":    dict(name="燕麥（乾重）", unit="100 g", c=663, p=169, f=69, src="USDA FDC 169705 Oats：碳水 66.3 g、蛋白質 16.9 g、脂肪 6.9 g／100 g（乾重）"),
 "banana":  dict(name="香蕉（中型 118 g）", unit="根", c=270, p=13, f=4, src="USDA FDC 173944 Bananas, raw，中型 118 g：碳水 27.0 g、蛋白質 1.3 g、脂肪 0.4 g"),
 "egg":     dict(name="雞蛋（大顆 50 g，水煮）", unit="顆", c=6, p=63, f=53, src="USDA FDC 173424 Egg, whole, cooked, hard-boiled，大顆 50 g：蛋白質 6.3 g、脂肪 5.3 g、碳水 0.6 g"),
 "chicken": dict(name="雞胸肉（熟重，巴掌大）", unit="100 g", c=0, p=310, f=36, src="USDA FDC 171477 Chicken breast, meat only, cooked, roasted：蛋白質 31.0 g、脂肪 3.6 g、碳水 0 g／100 g"),
 "meiji":   dict(name="Meiji High Protein（350 ml）", unit="瓶", c=98, p=300, f=21, src="Meiji High Protein 350 ml：蛋白質 30.0 g（依你提供）；碳水 9.8 g、脂肪 2.1 g（巧克力口味瓶身標示；香蕉、綠茶口味碳水 8.1 g）"),
 "powder":  dict(name="蛋白粉", unit="份", c=0, p=350, f=0, src="蛋白粉 1 份：蛋白質 35.0 g（依你提供）；品牌未知，碳水與脂肪未計入"),
}
OATS_G = {"rest": 40, "str": 40, "easy": 60, "long": 80, "quality": 80, "prelong": 80, "race": 80, "load": 100}
CARB_GKG = {"rest": 3, "str": 3, "easy": 4, "long": 5, "quality": 5, "prelong": 5, "race": 5, "load": 8}
TIER_LABEL = {"rest": "休息日", "str": "肌力日", "easy": "輕鬆跑日", "long": "長跑日", "quality": "強度課日",
              "prelong": "長跑前一天", "race": "比賽日", "load": "肝醣超補日"}
FAT_G = 57          # 0.8 g/kg × 71 kg = 56.8 → 57 g
FAT_G_LOAD = 40
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
    if any("長跑" in e["type"] for e in runs): return "long"
    if any(k in e["type"] for e in runs for k in ("節奏", "間歇", "目標配速", "測試", "配速模擬")): return "quality"
    if any(e["kind"] == "run" and e["km"] >= 14 for e in tomorrow): return "prelong"
    if runs: return "easy"
    if any(e["kind"] == "str" for e in entries): return "str"
    return "rest"

def build():
    plan = make_plan.build()
    byd = {}
    for e in plan["days"]:
        byd.setdefault(e["date"], []).append(e)
    out = {}
    d = dt.date.fromisoformat(START)
    while d.isoformat() <= END:
        ds = d.isoformat(); ents = byd.get(ds, [])
        if not ents:
            d += dt.timedelta(days=1); continue
        tmr = byd.get((d + dt.timedelta(days=1)).isoformat(), [])
        tier = classify(ents, tmr)
        runs = [e for e in ents if e["kind"] in ("run", "race")]; strs = [e for e in ents if e["kind"] == "str"]
        has_run, has_str = bool(runs), bool(strs)
        C = hu(CARB_GKG[tier] * WEIGHT * 10); FAT = (FAT_G_LOAD if tier == "load" else FAT_G) * 10
        meals = []
        # 早餐
        if ds == HALF_RACE:
            base = [item("powder", 1), item("egg", 2), item("banana", 2)]
            bc = sum(i["c"] for i in base)
            rice_g = hu((RACE_BREAKFAST_C - bc) / F["rice"]["c"] * 100)
            meals.append(dict(slot="早餐（起跑前 3 小時）", items=base + [item("rice", rice_g)],
                              tips=[f"早餐碳水 {g1(RACE_BREAKFAST_C)} g（2 g/kg）；只吃平常吃過、低纖維的食物。"]))
            meals.append(dict(slot="比賽中", items=[], text_items=["能量膠 × 2（10 km、16 km 各 1 包，配水）"],
                              tips=["能量膠沒有指定品牌，碳水未計入今日總量；用 10/11、10/18 演練過的同一款。"]))
        else:
            meals.append(dict(slot="早餐", items=[item("powder", 1), item("egg", 2), item("oats", OATS_G[tier])], tips=[]))
        # 訓練前後（Meiji 第 1 瓶在訓練後）
        tr_items, tr_tips = [], []
        if ds == HALF_RACE:
            tr_items.append(item("meiji", 1, "賽後 30 分鐘內"))
            slot_tr = "賽後"
        elif has_run or has_str:
            if has_run: tr_items.append(item("banana", 1, "跑前 45 分鐘"))
            if has_run and has_str:
                tr_items.append(item("meiji", 1, "跑後 30 分鐘內"))
                tr_items.append(item("meiji", 1, "肌力後 30 分鐘內"))
            else:
                tr_items.append(item("meiji", 1, "訓練後 30 分鐘內"))
            slot_tr = "訓練前後"
        else:
            tr_items.append(item("meiji", 1, "下午點心"))
            slot_tr = "下午點心"
        n_meiji = sum(1 for i in tr_items if i["key"] == "meiji")
        late = [item("meiji", 1, "睡前")] if n_meiji < 2 else []
        # 加餐（只在肝醣超補日）
        snack = [item("banana", 2)] if tier == "load" else []
        # 已固定的碳水 → 剩下的分給午餐白飯、（加餐白飯）、晚餐
        fixed = [i for m in meals for i in m["items"]] + tr_items + late + snack
        lunch_fixed = [item("chicken", 100, "放進麻辣燙")]
        R = C - sums(fixed + lunch_fixed)[0]
        parts = 3 if tier == "load" else 2
        lunch_rice = round10(R / parts / F["rice"]["c"] * 100)
        lunch = lunch_fixed + [item("rice", lunch_rice)]
        meals.append(dict(slot="午餐", title="麻辣燙（不加辣）配白飯", items=lunch,
                          tips=["雞胸肉 100 g（或等量瘦肉：里肌、魚片、蝦）和青菜放進麻辣燙。",
                                "炸物（豆皮、炸豆包、油條）與加工丸子、餃類少拿。",
                                "湯不要喝（湯裡有油）。"]))
        if snack:
            snack.append(item("rice", lunch_rice))
            meals.append(dict(slot="加餐（下午）", items=snack, tips=["肝醣超補：碳水分散到多餐，選低纖維食物。"]))
        meals.append(dict(slot=slot_tr, items=tr_items, tips=(["訓練前後依實際訓練時間調整；香蕉在跑前 45 分鐘吃。"] if has_run and ds != HALF_RACE else [])))
        if late:
            meals.append(dict(slot="睡前", items=late, tips=[]))
        # 晚餐（自由）：剩餘預算
        used = [i for m in meals for i in m["items"]]
        uc, up, uf = sums(used)
        dc, dfat = C - uc, FAT - uf
        ex_key = "rice" if tier in ("rest", "str") else "pasta"
        ex_g = max(0, hu(dc / F[ex_key]["c"] * 100))
        ex = item(ex_key, ex_g)
        dp = ex["p"]
        other_fat = max(0, dfat - ex["f"])
        P = up + dp
        total_k = kcal_t(C, P, FAT)
        dinner = dict(carbs=g1(dc), protein=g1(dp), fat=g1(dfat), kcal=g1(kcal_t(dc, dp, dfat)),
                      example=dict(food=ex["name"], grams=ex_g, carbs=g1(ex["c"]), protein=g1(ex["p"]), fat=g1(ex["f"]),
                                   other_fat=g1(other_fat),
                                   text=f"{ex['name'].replace('（熟）','')} {ex_g} g（碳水 {g1(ex['c'])} g、蛋白質 {g1(ex['p'])} g、脂肪 {g1(ex['f'])} g）＋青菜＋烹調油／醬汁／配料脂肪 {g1(other_fat)} g"),
                      tips=["晚餐自由選，控制在上面的剩餘預算內。",
                            "蛋白質已由早餐、午餐與 2 瓶 Meiji 吃夠；晚餐加肉、魚或豆腐，請從脂肪預算扣。"])
        # 輸出格式
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
        prot_base = 1386
        prot_extra = P - prot_base
        notes = []
        if d.weekday() == 6:
            notes.append("週日：早上起床、如廁後空腹量體重、體脂、腰圍，記錄後回報。")
        if tier == "prelong":
            notes.append("明天長跑：今天碳水 5 g/kg，晚餐以白飯或義大利麵為主，少油、少纖維。")
        if tier == "load":
            notes.append("肝醣超補（10/23、10/24）：碳水 8 g/kg、脂肪 40 g；少油、少纖維，多喝水。")
        day = dict(date=ds, weekday="週" + WD[d.weekday()], week=ents[0]["week"], tier=tier,
                   tier_label=f"{TIER_LABEL[tier]}｜碳水 {CARB_GKG[tier]} g/kg", training=train,
                   targets=dict(carbs=g1(C), protein=g1(P), fat=g1(FAT), kcal=g1(total_k),
                                protein_note=f"固定 138.6 g＋主食與香蕉 {g1(prot_extra)} g",
                                carbs_gkg=CARB_GKG[tier], protein_gkg=f"{P/10/WEIGHT:.2f}", fat_gkg=f"{FAT/10/WEIGHT:.2f}"),
                   meals=mo, dinner=dinner, notes=notes, sunday=d.weekday() == 6)
        # 每日訊息可直接引用的一段文字
        def short(m):
            parts_ = [f"{i['name'].split('（')[0]} {i['amount']}" + (f"（{i['when']}）" if i["when"] and i["when"] != m["slot"] else "") for i in m["items"]] + m.get("text_items", [])
            return f"{m['slot']}：" + (m["title"] + "（" if m["title"] else "") + "、".join(parts_) + ("）" if m["title"] else "")
        day["text"] = (f"{ds[5:].replace('-', '/')}（{day['weekday']}）飲食｜{day['tier_label']}｜今日目標：碳水 {g1(C)} g、蛋白質 {g1(P)} g、脂肪 {g1(FAT)} g、熱量 {g1(total_k)} kcal。"
                       + "；".join([short(m) for m in mo if m["slot"] != "睡前"]
                                   + [f"晚餐（自由）剩餘：碳水 {dinner['carbs']} g、蛋白質 {dinner['protein']} g、脂肪 {dinner['fat']} g、{dinner['kcal']} kcal（例：{dinner['example']['text']}）"]
                                   + [short(m) for m in mo if m["slot"] == "睡前"]) + "。"
                       + "".join(notes))
        # 自我檢查：逐項加總＋晚餐預算＝當日目標
        ac, ap, af = sums(used)
        assert ac + dc == C and af + dfat == FAT and ap + dp == P, ds
        assert dc >= 0 and dfat >= 0, (ds, dc, dfat)
        out[ds] = day
        d += dt.timedelta(days=1)
    meta = dict(
        weight=WEIGHT, body_fat=BODY_FAT, body_fat_goal=BODY_FAT_GOAL, deficit=DEFICIT, start=START, end=END,
        summary=f"體重 {WEIGHT:g} kg、體脂 {BODY_FAT:g}%，目標 12/31 前體脂 {BODY_FAT_GOAL:g}%；每日熱量赤字目標 {DEFICIT} kcal。",
        rules=[f"碳水：休息日與肌力日 3 g/kg（213 g）；輕鬆跑／恢復跑日 4 g/kg（284 g）；長跑日、強度課日、10K 測試日與 14 km 以上長跑的前一天 5 g/kg（355 g）；10/23、10/24 肝醣超補 8 g/kg（568 g）。",
               "蛋白質：固定 138.6 g＝Meiji 30 g × 2 瓶（60.0）＋蛋白粉 1 份（35.0）＋雞蛋 × 2（12.6）＋雞胸肉 100 g（31.0），再加上白飯、義大利麵、燕麥、香蕉的蛋白質。",
               f"脂肪：0.8 g/kg（57 g）；肝醣超補日 40 g。熱量＝碳水 × 4＋蛋白質 × 4＋脂肪 × 9。"],
        footnotes=[
            "每公斤體重的碳水、蛋白質、脂肪建議依據：ACSM／美國營養與飲食學會／加拿大營養師協會 2016 聯合立場聲明（Thomas et al., Med Sci Sports Exerc 48:543）與 ISSN 立場聲明（Jäger et al. 2017 蛋白質與運動；Kerksick et al. 2017 營養時機）。",
            "麻辣燙的湯、油與青菜沒有計入（份量與用油每家不同），請不要喝湯；表中只計白飯、雞胸肉等有明確數值的食物。",
            "蛋白粉品牌未知，只計蛋白質 35.0 g；能量膠品牌未知，碳水未計入。Meiji 碳水與脂肪以巧克力口味瓶身標示計。",
            "身高、年齡、性別未提供，所以不計算也不顯示 TDEE；熱量赤字 183 kcal／天是目標值，請以每週日的體重、體脂、腰圍趨勢檢查。",
        ] + ["食物數值：" + F[k]["src"] for k in ("rice", "pasta", "oats", "banana", "egg", "chicken", "meiji", "powder")],
    )
    return dict(meta=meta, days=out)

if __name__ == "__main__":
    import sys, os
    p = build()
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    json.dump(p, open(os.path.join(out, "data/diet.json"), "w"), ensure_ascii=False, indent=1)
