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
ACTIVITY = float(_B.get("activity_factor", 1.2))   # 日常活動係數（運動另外加）；2026-10-06 曾依 Pixel Watch 改 1.3，同日使用者覺得熱量太多改回 1.2（profile.json）
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
 "cabbage": dict(name="高麗菜（生重）", unit="100 g", c=58, p=12.8, f=1, src="USDA FDC 169975 Cabbage, raw：碳水 5.8 g、蛋白質 1.28 g、脂肪 0.1 g／100 g"),
 "tofu":    dict(name="豆腐（板豆腐）", unit="100 g", c=18.7, p=80.8, f=47.8, src="USDA FDC 172476 Tofu, raw, regular, prepared with calcium sulfate：碳水 1.87 g、蛋白質 8.08 g、脂肪 4.78 g／100 g"),
 "steak":   dict(name="沙朗牛肉（熟）", unit="100 g", c=0, p=270, f=142, src="USDA FDC 168727 Beef, top sirloin, steak, separable lean and fat, trimmed to 1/8\" fat, all grades, cooked, broiled：蛋白質 27.0 g、脂肪 14.2 g、碳水 0 g／100 g"),
 "pork":    dict(name="梅花豬（烤，熟）", unit="100 g", c=0, p=255.8, f=166.1, src="USDA FDC 167851 Pork, fresh, shoulder, blade, boston (steaks), separable lean and fat, cooked, broiled：蛋白質 25.58 g、脂肪 16.61 g、碳水 0 g／100 g"),
 "salmon":  dict(name="鮭魚（生魚片）", unit="100 g", c=0, p=204.2, f=134.2, src="USDA FDC 175167 Fish, salmon, Atlantic, farmed, raw：蛋白質 20.42 g、脂肪 13.42 g、碳水 0 g／100 g"),
 "whopper": dict(name="華堡（Whopper）", unit="個", c=521.9, p=251.5, f=355.2, src="漢堡王新加坡營養資訊（sgmenu.org 轉載官方資料）：華堡 Whopper 1 個 碳水 52.19 g、蛋白質 25.15 g、脂肪 35.52 g"),
 "whopperjr": dict(name="華堡 Jr.（Whopper Jr.）", unit="個", c=323.9, p=152.7, f=200.9, src="漢堡王新加坡營養資訊（sgmenu.org 轉載官方資料）：華堡 Jr. 1 個 碳水 32.39 g、蛋白質 15.27 g、脂肪 20.09 g"),
 "bkfries": dict(name="小薯（French Fries S）", unit="份", c=312.0, p=29.9, f=51.4, src="漢堡王新加坡營養資訊（sgmenu.org 轉載官方資料）：小薯 French Fries (S) 1 份 碳水 31.20 g、蛋白質 2.99 g、脂肪 5.14 g；零卡飲料以 0 計"),
 "bread":   dict(name="白吐司（加餐碳水）", unit="100 g", c=494.2, p=88.5, f=33.3, src="USDA FDC 174924 Bread, white, commercially prepared：碳水 49.42 g、蛋白質 8.85 g、脂肪 3.33 g／100 g"),
 "ricenoodle": dict(name="米粉／河粉（熟）", unit="100 g", c=240.1, p=17.9, f=2, src="USDA FDC 168914 Rice noodles, cooked：碳水 24.01 g、蛋白質 1.79 g、脂肪 0.2 g／100 g"),
 "eggnoodle": dict(name="黃麵（雞蛋麵，熟）", unit="100 g", c=251.6, p=45.4, f=20.7, src="USDA FDC 169732 Noodles, egg, enriched, cooked：碳水 25.16 g、蛋白質 4.54 g、脂肪 2.07 g／100 g"),
 "fish":    dict(name="魚片（鯛魚，熟）", unit="100 g", c=0, p=263, f=17.2, src="USDA FDC 173699 Fish, snapper, mixed species, cooked, dry heat：蛋白質 26.3 g、脂肪 1.72 g、碳水 0 g／100 g"),
 "shrimp":  dict(name="鮮蝦（熟）", unit="100 g", c=2, p=240, f=2.8, src="USDA FDC 175180 Crustaceans, shrimp, cooked：蛋白質 24.0 g、脂肪 0.28 g、碳水 0.2 g／100 g"),
 "tomato":  dict(name="番茄", unit="100 g", c=38.9, p=8.8, f=2, src="USDA FDC 170457 Tomatoes, red, ripe, raw：碳水 3.89 g、蛋白質 0.88 g、脂肪 0.2 g／100 g"),
 "sz_bolo": dict(name="薩莉亞 肉醬義大利麵（Spaghetti Bolognese）", unit="份", c=802, p=192, f=160, src="薩莉亞新加坡未公開營養成分；以薩莉亞日本（kalori.jp 推定值）ミートソースボロニア風 1 份：碳水 80.2 g、蛋白質 19.2 g、脂肪 16.0 g"),
 "sz_doria": dict(name="薩莉亞 米蘭風焗飯（Milano Style Doria）", unit="份", c=723, p=167, f=222, src="薩莉亞新加坡未公開營養成分；以薩莉亞日本（kalori.jp 推定值）ミラノ風ドリア 1 份：碳水 72.3 g、蛋白質 16.7 g、脂肪 22.2 g"),
 "sz_hamburg": dict(name="薩莉亞 漢堡排（Hamburg Steak）", unit="份", c=210, p=307, f=389, src="薩莉亞新加坡未公開營養成分；以薩莉亞日本（kalori.jp 推定值）ハンバーグステーキ 1 份：碳水 21.0 g、蛋白質 30.7 g、脂肪 38.9 g"),
 "sz_chicken": dict(name="薩莉亞 辣味烤雞（Grilled Chicken Diavola）", unit="份", c=314, p=502, f=486, src="薩莉亞新加坡未公開營養成分；以薩莉亞日本（kalori.jp 推定值）若鶏のディアボラ風 1 份：碳水 31.4 g、蛋白質 50.2 g、脂肪 48.6 g"),
 "sz_salad": dict(name="薩莉亞 芝麻菜雞肉沙拉（Arugula Chicken Salad）", unit="份", c=176, p=419, f=32, src="薩莉亞新加坡未公開營養成分；以薩莉亞日本（kalori.jp 推定值）チキンのサラダ 1 份：碳水 17.6 g、蛋白質 41.9 g、脂肪 3.2 g；醬汁另放、少量"),
 "banana":  dict(name="香蕉（中型 118 g）", unit="根", c=270, p=13, f=4, src="USDA FDC 173944 Bananas, raw，中型 118 g：碳水 27.0 g、蛋白質 1.3 g、脂肪 0.4 g"),
 "egg":     dict(name="雞蛋（大顆 50 g，水煮）", unit="顆", c=6, p=63, f=53, src="USDA FDC 173424 Egg, whole, cooked, hard-boiled，大顆 50 g：蛋白質 6.3 g、脂肪 5.3 g、碳水 0.6 g"),
 "chicken": dict(name="雞胸肉（熟重，巴掌大）", unit="100 g", c=0, p=310, f=36, src="USDA FDC 171477 Chicken breast, meat only, cooked, roasted：蛋白質 31.0 g、脂肪 3.6 g、碳水 0 g／100 g"),
 "porkloin": dict(name="肉片（里肌，熟）", unit="100 g", c=0, p=262, f=36, src="USDA FDC 168250 Pork, fresh, loin, tenderloin, separable lean only, cooked, roasted：每 100 g 蛋白質 26.18 g、脂肪 3.51 g、碳水 0 g；本表取 0.1 g（蛋白質 26.2 g、脂肪 3.6 g，脂肪由 3.51 四捨五入到 3.6，午餐 4/4/9 才剛好 700.0 kcal）"),
 "meiji":   dict(name="Meiji High Protein（350 ml）", unit="瓶", c=98, p=300, f=21, src="Meiji High Protein 350 ml：蛋白質 30.0 g（依你提供）；碳水 9.8 g、脂肪 2.1 g（巧克力口味瓶身標示；香蕉、綠茶口味碳水 8.1 g）"),
 "creatine": dict(name="肌酸", unit="100 g", c=0, p=0, f=0, src="肌酸（一水肌酸）5 g：熱量、蛋白質、碳水、脂肪皆以 0 計，不影響任何目標"),
 "powder":  dict(name="蛋白粉", unit="份", c=0, p=350, f=0, src="蛋白粉 1 份：蛋白質 35.0 g（依你提供）；品牌未知，碳水與脂肪未計入"),
}
# 午餐固定：麻辣燙（不加辣）＝肉片（里肌）160.6 g＋高麗菜 300 g，配白飯 310.5 g（2026-10-09 使用者：麻辣燙沒有豆腐；豆腐 100 g 的 83.2 kcal 改給肉片）。
# 肉片克數＝(700.0 − 高麗菜 − 白飯) ÷ 1.372 kcal/g＝220.4 ÷ 1.372＝160.64 g → 160.6 g。各營養素以 0.1 g 計時，任何 0.1 g 肉片克數都無法剛好 700.0（160.4 g＝699.8、160.5–160.8 g＝700.2），所以 LUNCH_KCAL_T＝7002（700.2 kcal）。
# 2026-10-09 使用者：「中午都是肉片不會有雞胸」。肉片用 USDA 里肌瘦肉；白飯由 295 g 改 310.5 g，4/4/9 仍剛好 700.0 kcal。湯與油不計。
LUNCH_RICE_G, LUNCH_KCAL_T = 310.5, 7002
LUNCH_PORK_G = 160.6
CARB_GKG = {"rest": 3, "str": 3, "easy": 4, "long": 5, "quality": 5, "prelong": 5, "race": 5, "load": 8}
TIER_LABEL = {"rest": "休息日", "str": "肌力日", "easy": "輕鬆跑日", "long": "長跑日", "quality": "強度課日",
              "prelong": "長跑前一天", "race": "比賽日", "load": "肝醣超補日"}
LOAD_DAYS = {"2026-10-23", "2026-10-24"}
# 週末吃好點（2026-10-06 使用者「週末可以吃好點」）：每週平日晚餐 −100.0 kcal、週六日 +250.0 kcal，週總量不變。
# 半馬週 10/19–10/25 不調整；不完整的週：平日照扣 100，週末平分扣下來的總量（10/10、10/11 各 +200.0）；沒有週末的週（12/28–12/31）不調整。
SHIFT_WD_T = -1000
NO_SHIFT_WEEKS = {"2026-10-19", "2026-12-21"}   # 半馬週；12/27 10K 測試週
# 週末晚餐參考例（使用者指定：燒肉、牛排、丼飯）輪替：（名稱, 肉／魚, 標準克數, 主食）。肉的克數放不進晚餐脂肪預算時每次減 10 g。長跑前一天固定用鮭魚丼（以飯為主、少油）。
# 漢堡王（新加坡）：華堡＋小薯 1 份＋零卡飲料；脂肪預算放不下華堡時改華堡 Jr.，再放不下（或碳水超過預算）就改用下一個參考例；剩下的碳水、脂肪另列。
def _meat(key, std, extra=()):   # 肉／魚每次 −10 g 的份量層級
    return [[(key, g)] + list(extra) for g in range(std, 0, -10)]
# 晚餐參考例（DISHES）：variants＝固定部分（由大到小，放不進晚餐脂肪預算就用下一個），base＝補足晚餐碳水的主食（熟重上限 MAX_BASE_G），
# 主食到上限還不夠的碳水另列「加餐碳水」白吐司。肉／魚／餐點的蛋白質算進晚餐蛋白質預算。
MAX_BASE_G = 400
SLOT_ID = {"早餐": "bf", "早餐（起跑前 3 小時）": "bf", "午餐": "lunch", "加餐（下午）": "snack", "訓練前後": "pre", "晚餐": "dinner"}   # 打勾紀錄的餐次代號
SZ_MIN_RICE_G = 50
DISHES = {
 "燒肉（梅花豬）配白飯": dict(v=_meat("pork", 150), base="rice"),
 "牛排配義大利麵": dict(v=_meat("steak", 150), base="pasta"),
 "漢堡王": dict(v=[[("whopper", 1), ("bkfries", 1)], [("whopperjr", 1), ("bkfries", 1)]], base=None),
 "牛丼": dict(v=_meat("steak", 150), base="rice"),
 "鮭魚丼": dict(v=_meat("salmon", 120), base="rice"),
 "海南雞飯（雞胸）": dict(v=_meat("chicken", 100), base="rice"),
 "魚片米粉湯": dict(v=_meat("fish", 120), base="ricenoodle", bl={"ricenoodle": "米粉"}),
 "番茄炒蛋飯": dict(v=[[("egg", 2), ("tomato", 150)], [("egg", 1), ("tomato", 150)]], base="rice"),
 "照燒雞便當": dict(v=_meat("chicken", 100), base="rice"),
 "蝦麵": dict(v=_meat("shrimp", 100), base="eggnoodle"),
 "越南牛肉河粉": dict(v=_meat("steak", 80), base="ricenoodle", bl={"ricenoodle": "河粉"}),
 "雞肉義大利麵": dict(v=_meat("chicken", 100), base="pasta"),
 "魚片湯配白飯": dict(v=_meat("fish", 120), base="rice"),
 "薩莉亞 肉醬義大利麵": dict(v=[[("sz_bolo", 1)]], base="rice", sz=True, bl={"rice": "加點白飯（Steamed Rice）"}),
 "薩莉亞 芝麻菜雞肉沙拉配白飯": dict(v=[[("sz_salad", 1)]], base="rice", sz=True, bl={"rice": "加點白飯（Steamed Rice）"}),
 "薩莉亞 米蘭風焗飯": dict(v=[[("sz_doria", 1)]], base="rice", sz=True, bl={"rice": "加點白飯（Steamed Rice）"}),
 "薩莉亞 漢堡排配白飯": dict(v=[[("sz_hamburg", 1)]], base="rice", sz=True, bl={"rice": "加點白飯（Steamed Rice）"}),
 "薩莉亞 辣味烤雞配白飯": dict(v=[[("sz_chicken", 1)]], base="rice", sz=True, bl={"rice": "加點白飯（Steamed Rice）"}),
}
# 週末（吃好點）輪替：燒肉、牛排、漢堡王、牛丼、鮭魚丼（長跑前一天固定鮭魚丼）。漢堡王放不下時，下一個放得下的週末日優先。
TREATS = ["燒肉（梅花豬）配白飯", "牛排配義大利麵", "漢堡王", "牛丼", "鮭魚丼"]
TREAT_PRELONG = 4
# 平日（與不調整的週末）輪替：8 道，相鄰兩天不重複；每週 2 個平日排薩莉亞（選放得下預算、盡量不相鄰的 2 天）。
WD_ROT = ["海南雞飯（雞胸）", "魚片米粉湯", "番茄炒蛋飯", "照燒雞便當", "蝦麵", "越南牛肉河粉", "雞肉義大利麵", "魚片湯配白飯"]
SZ_ROT = ["薩莉亞 肉醬義大利麵", "薩莉亞 芝麻菜雞肉沙拉配白飯", "薩莉亞 米蘭風焗飯", "薩莉亞 漢堡排配白飯", "薩莉亞 辣味烤雞配白飯"]
DINNER_FLOOR_T = 4500   # 平日晚餐剩餘下限 450.0 kcal：−100 會低於 450 時，只扣到 450，週末加成同步減少
HALF_RACE = "2026-10-25"
CREATINE_FROM = "2026-10-09"   # 2026-10-09 起每天早餐加肌酸 5 g（0 kcal、0 g 蛋白質，可打勾，id bf-creatine）
RACE_BREAKFAST_C = 1420   # 142 g（2 g/kg），起跑前 3 小時

def hu(x):  # 四捨五入到整數（十分之一克）
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)

UNIT_WORD = {"powder": "份", "egg": "顆", "banana": "根", "meiji": "瓶", "whopper": "個", "whopperjr": "個", "bkfries": "份",
             "sz_bolo": "份", "sz_doria": "份", "sz_hamburg": "份", "sz_chicken": "份", "sz_salad": "份"}

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

def _pn(q):   # 參考例裡的品名（去掉括號說明）
    n = q["name"]
    for t in ("（熟）", "（烤，熟）", "（生魚片）", "（Whopper）", "（Whopper Jr.）", "（French Fries S）", "（鯛魚，熟）", "（里肌，熟）", "（雞蛋麵，熟）", "（加餐碳水）", "（熟重，巴掌大）", "（大顆 50 g，水煮）"):
        n = n.replace(t, "")
    return n

def _mac(c, p, f):
    return f"碳水 {g1(c)} g、蛋白質 {g1(p)} g、脂肪 {g1(f)} g"

def dish_example(ex, dc, other_fat):
    """晚餐參考例：餐點各部分＋（主食到 400 g 上限時）另列的加餐碳水。"""
    parts = [q for q in ex["parts"] if not (q["key"] == DISHES[ex["name"]]["base"] and q["c"] == 0)]
    mc, mp, mf = sums(parts)
    bl = DISHES[ex["name"]].get("bl", {})
    sz = DISHES[ex["name"]].get("sz")
    nm = lambda q: bl.get(q["key"], ("點 " if sz and q["key"].startswith("sz_") else "") + _pn(q).replace("薩莉亞 ", ""))
    body = "＋".join(f"{nm(q)} {q['amount']}" for q in parts)
    out = dict(food=ex["name"], treat=True, parts=[dict(name=nm(q), amount=q["amount"], carbs=g1(q["c"]), protein=g1(q["p"]), fat=g1(q["f"])) for q in parts],
               carbs=g1(ex["c"]), protein=g1(ex["p"]), fat=g1(ex["f"]), other_fat=g1(other_fat))
    if ex["name"] == "漢堡王":
        out["text"] = f"漢堡王：{body}＋零卡飲料（{_mac(mc, mp, mf)}）" + (f"；還剩碳水 {g1(dc - ex['c'])} g、脂肪 {g1(other_fat)} g" if dc - ex["c"] > 0 or other_fat > 0 else "")
    else:
        left = dc - ex["c"]
        out["text"] = f"{ex['name']}：{body}（{_mac(mc, mp, mf)}）＋青菜＋醬料／油脂 {g1(other_fat)} g" + (f"；還剩碳水 {g1(left)} g" if left >= 10 else "")
    sn = ex.get("snack")
    if sn:
        out["snack"] = dict(name=_pn(sn), amount=sn["amount"], carbs=g1(sn["c"]), protein=g1(sn["p"]), fat=g1(sn["f"]))
        out["snack_text"] = f"白吐司 {sn['amount']}（{_mac(sn['c'], sn['p'], sn['f'])}）：主食已到 {MAX_BASE_G} g 上限，多的碳水 {g1(sn['c'])} g 改用加餐補（可換成同樣碳水 {g1(sn['c'])} g 的香蕉、果汁或運動飲料）"
    return out

def shifts_for(p0):
    """依沒有移轉時的晚餐剩餘（p0）算每日移轉：平日 −100（晚餐不低於 450），週末平分平日扣下來的總量。"""
    SH, info = {}, dict(floor=[], below=[])
    wk = {}
    for k, x in sorted(p0["days"].items()): wk.setdefault(x["week"], []).append(k)
    for w, ks in sorted(wk.items()):
        wd = [k for k in ks if dt.date.fromisoformat(k).weekday() < 5]; we = [k for k in ks if dt.date.fromisoformat(k).weekday() >= 5]
        if w in NO_SHIFT_WEEKS or not we: continue
        tot = 0
        for k in wd:
            d0 = hu(float(p0["days"][k]["dinner"]["kcal"]) * 10)
            cut = min(-SHIFT_WD_T, max(0, d0 - DINNER_FLOOR_T))
            if cut < -SHIFT_WD_T: (info["floor"] if cut > 0 else info["below"]).append((k, g1(d0), g1(cut)))
            SH[k] = -cut; tot += cut
        base, extra = divmod(tot, len(we))
        for i, k in enumerate(we): SH[k] = base + (1 if i < extra else 0)
    assert sum(SH.values()) == 0
    return SH, info

def pick_sz(pp):
    """每週選 2 個放得下薩莉亞的平日（盡量不相鄰），薩莉亞品項依序輪替。"""
    wk, out, short = {}, {}, []
    for k, x in sorted(pp["days"].items()):
        if "_szfit" in x: wk.setdefault(x["week"], []).append(k)
    ptr = 0
    for w, ks in sorted(wk.items()):
        ok = [k for k in ks if pp["days"][k]["_szfit"]]
        pairs = [(a, b) for i, a in enumerate(ok) for b in ok[i + 1:]]
        dist = lambda a, b: (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
        chosen = list(max(pairs, key=lambda ab: (min(dist(*ab), 2), -ok.index(ab[0])))) if pairs else ok[:1]
        if len(chosen) < 2: short.append((w, len(chosen)))
        for k in chosen:
            fit = pp["days"][k]["_szfit"]
            order = [SZ_ROT[(ptr + j) % len(SZ_ROT)] for j in range(len(SZ_ROT))]
            out[k] = [n for n in order if n in fit]
            ptr = (SZ_ROT.index(out[k][0]) + 1) % len(SZ_ROT)
    return out, short

def build():
    """先用 183 算出 D 以外的日子的缺口，反推 10/26 起一般日的統一缺口 D；再依晚餐剩餘算週末移轉、選薩莉亞日，最後重算。"""
    first = _build(DEFICIT * 10, {}, {})
    days = first["days"]
    flex = [k for k, x in days.items() if x["energy"]["flex"]]
    g0 = lambda x: x["energy"]["gap_t"] + x["energy"]["shift_t"]     # 週末移轉前的缺口（每週移轉合計 0）
    fixed_gap = sum(g0(x) for k, x in days.items() if k not in flex)
    need = GOAL_T - fixed_gap
    d_t = int(need / len(flex) + 0.5) if flex else 0
    capped = d_t > hu(D_CAP * 10)
    if capped: d_t = hu(D_CAP * 10)
    p1 = _build(d_t, {}, {})
    pp = _build(d_t, {}, {}, probe=True)   # 2026-10-09：不再做平日／週末熱量移轉（含晚餐 450 下限與週末加成）
    SZ, sz_short = pick_sz(pp)
    p = _build(d_t, {}, SZ)
    global LAST_INFO   # 報告用（不寫進 diet.json）
    LAST_INFO = dict(floor=[], below=[], sz_short=sz_short, sz_days=sorted(SZ))
    total = sum(x["energy"]["gap_t"] for x in p["days"].values())
    pre = sum(x["energy"]["gap_t"] for k, x in p["days"].items() if k <= "2026-10-25")
    assert all(g0(p["days"][k]) == d_t for k in flex)
    short = GOAL_T - total
    p["meta"]["goal"] = dict(goal=g1(GOAL_T), total=g1(total), through_1025=g1(pre), d=g1(d_t), flex_days=len(flex),
                             fixed_gap=g1(fixed_gap), capped=capped, shortfall=g1(short) if capped else "0.0",
                             text=f"12/31 前總熱量缺口目標 {g1(GOAL_T).replace('.0', '')} kcal（{FAT_LOSS_KG:g} kg 脂肪 × {KCAL_PER_KG}），目前計畫合計 {g1(total)} kcal"
                                  + (f"；10/26 起一般日每天缺口 {g1(d_t)} kcal" if not capped else f"；每天缺口已到上限 {D_CAP:g} kcal，仍差 {g1(short)} kcal"))
    return p

def _build(late_def_t, SHIFT, SZ_DAY, probe=False):
    plan = make_plan.build()
    byd = {}
    for e in plan["days"]:
        byd.setdefault(e["date"], []).append(e)
    out = {}
    # ---- 週末吃好點：移轉（SHIFT，十分之一 kcal，由 build() 算好傳入）與週末參考例
    TREAT = {}
    wk = {}
    for k in sorted(byd):
        if START <= k <= END: wk.setdefault(byd[k][0]["week"], []).append(k)
    ti, prev = 0, None
    for w, ks in sorted(wk.items()):
        we = [k for k in ks if dt.date.fromisoformat(k).weekday() >= 5]
        if w in NO_SHIFT_WEEKS: continue
        for k in we:   # 2026-10-09：取消平日 −100／週末 +250；週末仍用吃好點參考例，份量依未移轉的晚餐剩餘
            tmr0 = byd.get((dt.date.fromisoformat(k) + dt.timedelta(days=1)).isoformat(), [])
            if classify(byd[k], tmr0) == "prelong": TREAT[k] = TREAT_PRELONG
            else:
                if ti % len(TREATS) == prev: ti += 1
                TREAT[k] = ti % len(TREATS); ti += 1
            prev = TREAT[k]
    PREV_TR, BK_PENDING, WD_PTR = [None], [False], [0]
    def wk_cut(k):   # 本週平日共扣多少（十分之一 kcal）
        w = byd[k][0]["week"]
        return sum(-SHIFT.get(x, 0) for x in wk.get(w, []) if dt.date.fromisoformat(x).weekday() < 5)
    BMR_T = hu(BMR * 10); BASE_T = hu(BMR * ACTIVITY * 10); FLOOR_T = hu(FAT_FLOOR * WEIGHT * 10); CAP_T = hu(FAT_CAP * WEIGHT * 10)
    FIXED_P = item("egg", 2)["p"] + item("meiji", 2)["p"] + item("porkloin", LUNCH_PORK_G)["p"]   # 雞蛋 2 顆＋Meiji 2 瓶＋午餐肉片 160.6 g（2026-10-09 午餐拿掉豆腐）（2026-10-09 起不再含蛋白粉、雞胸）
    PROT_MIN_T = 1300   # 每天蛋白質至少 130.0 g（1.83 g/kg）
    d = dt.date.fromisoformat(START)
    while d.isoformat() <= END:
        ds = d.isoformat(); ents = byd.get(ds, [])
        if not ents:
            d += dt.timedelta(days=1); continue
        tmr = byd.get((d + dt.timedelta(days=1)).isoformat(), [])
        tier = classify(ents, tmr)
        runs = [e for e in ents if e["kind"] in ("run", "race")]; strs = [e for e in ents if e["kind"] == "str"]
        has_run, has_str = bool(runs), bool(strs)
        # ---- 熱量：TDEE＝BMR × ACTIVITY（profile.json，目前 1.2）＋運動
        EX_T, ex_parts = exercise(ents)
        TDEE_T = BASE_T + EX_T
        C_TIER = hu(CARB_GKG[tier] * WEIGHT * 10)
        # ---- 固定餐點
        meals = []
        if ds == HALF_RACE:
            base = [item("egg", 2), item("meiji", 1), item("banana", 2)]   # 2026-10-09：早餐不喝蛋白粉
            bc = sum(i["c"] for i in base)
            rice_g = hu((RACE_BREAKFAST_C - bc) / F["rice"]["c"] * 100)
            meals.append(dict(slot="早餐（起跑前 3 小時）", items=base + [item("rice", rice_g)] + ([item("creatine", 5)] if ds >= CREATINE_FROM else []),
                              tips=[f"早餐碳水 {g1(RACE_BREAKFAST_C)} g（2 g/kg）；只吃平常吃過、低纖維的食物。"]))
            meals.append(dict(slot="比賽中", items=[], text_items=["能量膠 × 2（10 km、16 km 各 1 包，配水）"],
                              tips=["能量膠沒有指定品牌，碳水未計入今日總量；用 10/11、10/18 演練過的同一款。"]))
        else:
            meals.append(dict(slot="早餐", items=[item("egg", 2), item("meiji", 1)] + ([item("creatine", 5)] if ds >= CREATINE_FROM else []), tips=[]))   # 2026-10-09：早餐不喝蛋白粉（太飽），只留雞蛋 2 顆＋Meiji 1 瓶；少掉的熱量由晚餐吸收
        # 2026-10-06 使用者：Meiji 改為早餐 1 瓶、晚餐 1 瓶（不再放訓練後／下午點心／睡前）
        tr_items = []
        if has_run and ds != HALF_RACE: tr_items.append(item("banana", 1, "跑前 45 分鐘"))
        slot_tr = "訓練前後"
        dinner_fixed = [item("meiji", 1, "晚餐")]
        snack_fixed = [item("banana", 2)] if tier == "load" else []
        lunch_fixed = [item("porkloin", LUNCH_PORK_G, "放進麻辣燙"), item("cabbage", 300, "放進麻辣燙"), item("rice", LUNCH_RICE_G)]   # 2026-10-09：沒有豆腐
        assert kcal_t(*sums(lunch_fixed)) == LUNCH_KCAL_T, (ds, kcal_t(*sums(lunch_fixed)))
        fixed = [i for m in meals for i in m["items"]] + tr_items + snack_fixed + lunch_fixed + dinner_fixed
        fc, fp, ff = sums(fixed)
        # 午餐固定；只有肝醣超補日有下午加餐白飯（剩餘碳水的一半，取 10 g 整數），其餘由晚餐吸收
        rice0 = round10((C_TIER - fc) / 2 / F["rice"]["c"] * 100) if tier == "load" else 0
        ex_key = "rice" if tier in ("rest", "str") else "pasta"
        SH = SHIFT.get(ds, 0)
        nodish = tier == "load" or ds == HALF_RACE          # 肝醣超補日、半馬當天維持原本的主食參考例
        if nodish: TRC = [None]
        elif ds in TREAT:                                     # 週末吃好點：放不進預算時依序改用下一個
            TRC = [TREATS[(TREAT[ds] + j) % len(TREATS)] for j in range(len(TREATS))]
            if TREAT[ds] != TREAT_PRELONG and BK_PENDING[0]:  # 上次輪到漢堡王但預算放不下，就在下一個放得下的週末日優先
                TRC = [T for T in TRC if T == "漢堡王"] + [T for T in TRC if T != "漢堡王"]
        else:                                                 # 平日輪替（薩莉亞日先試薩莉亞）
            TRC = SZ_DAY.get(ds, []) + [WD_ROT[(WD_PTR[0] + j) % len(WD_ROT)] for j in range(len(WD_ROT))]
        if not nodish: TRC = [T for T in TRC if T != PREV_TR[0]]      # 相鄰兩天不重複（含平日／週末交界）
        TR = TRC[0]
        def levels(T):   # 份量層級：肉／魚每次 −10 g；漢堡王 華堡 → 華堡 Jr.
            return DISHES[T]["v"] if T else [None]
        tg = [levels(TR)[0]]
        def ex_for(dc):
            if not TR:
                return item(ex_key, max(0, hu(dc / F[ex_key]["c"] * 100)))
            Dd = DISHES[TR]
            parts = [item(k, q) for k, q in tg[0]]
            pc = sum(q["c"] for q in parts); need = dc - pc; snack = None
            if Dd["base"]:
                g = min(MAX_BASE_G, max(0, hu(need / F[Dd["base"]]["c"] * 100)))
                if Dd.get("sz") and pc >= 500 and g < SZ_MIN_RICE_G: g = 0          # 薩莉亞加點白飯太少就不點，剩下的碳水列在後面
                bi = item(Dd["base"], g); parts.append(bi); need -= bi["c"]
                if g == MAX_BASE_G and need > 0:                # 主食已到 400 g：多的碳水另列加餐（白吐司）
                    sg = hu(need / F["bread"]["c"] * 100)
                    if sg > 0: snack = item("bread", sg, "晚餐後加餐")
            c, p, f = sums(parts + ([snack] if snack else []))
            return dict(key="dish", name=TR, amount="", parts=parts, snack=snack, pc=pc, c=c, p=p, f=f)
        def rice_items(sr):   # 午餐白飯已在 lunch_fixed；這裡只有肝醣超補日的下午加餐白飯
            return [item("rice", sr)] if tier == "load" else []
        def solve_one():
            # ---- 解
            sr = rice0
            rc, rp, rf = sums(rice_items(sr))
            pk = 0; mode = "normal"; adj = None; flex = False; day_def = 0
            def solve_fixed(Ff, low):
                """脂肪固定在 Ff（下限或上限），晚餐碳水補到剛好（午餐固定 700.0 kcal，不調整）。"""
                ep = 0
                for _ in range(5):
                    dc = (TK - 9 * Ff - 4 * (fc + rc) - 4 * (fp + rp + ep)) // 4
                    ep = ex_for(max(dc, 0))["p"]
                rem = TK - 4 * (fc + rc + dc) - 4 * (fp + rp + ep)
                rng = range(Ff, Ff + 4) if low else range(Ff - 3, Ff + 1)
                ok = [f for f in rng if (rem - 9 * f) % 4 == 0]
                F_ = min(ok) if low else max(ok)
                dc += (rem - 9 * F_) // 4           # 0.1 kcal 尾數由晚餐碳水吸收
                return dc, ep, F_
            if tier == "load" or ds == HALF_RACE or tier == "prelong":
                mode = "load" if tier == "load" else ("race" if ds == HALF_RACE else "prelong")
                FAT_T = {"load": hu(FAT_LOAD * 10), "race": hu(FAT_RACE * 10), "prelong": FLOOR_T}[mode]
                dc = C_TIER - fc - rc
                ep = item(ex_key, max(0, hu(dc / F[ex_key]["c"] * 100)))["p"] if not TR else ex_for(dc)["p"]
                if TR or SH:   # 週末吃好點：目標＝原本的公式值（用平常的主食參考例算蛋白質）＋移轉；脂肪維持下限，差額全部由晚餐碳水吸收
                    ep = item(ex_key, max(0, hu(dc / F[ex_key]["c"] * 100)))["p"]
                    TK = 4 * C_TIER + 4 * (fp + rp + ep) + 9 * FAT_T + SH
                    dc, ep, FAT_T = solve_fixed(FAT_T, True)
                else:
                    TK = 4 * C_TIER + 4 * (fp + rp + ep) + 9 * FAT_T
            else:
                flex = ds >= D_START and not (tier == "race")          # 12/27 10K 測試日維持 183
                day_def = late_def_t if flex else DEFICIT * 10
                TK = TDEE_T - day_def + SH
                dc = C_TIER - fc - rc
                ep = ex_for(dc)["p"]
                rem = TK - 4 * C_TIER - 4 * (fp + rp + ep)
                cands = [f for f in range(rem // 9 - 4, rem // 9 + 5) if (rem - 9 * f) % 4 == 0]
                FAT_T = min(cands, key=lambda f: abs(rem - 9 * f))
                pk = (rem - 9 * FAT_T) // 4          # 0.1 g 等級的熱量尾數，由晚餐蛋白質預算吸收
                if FAT_T < FLOOR_T:
                    adj = "floor"; pk = 0
                    dc, ep, FAT_T = solve_fixed(FLOOR_T, True)
                elif FAT_T > CAP_T:
                    adj = "cap"; pk = 0
                    dc, ep, FAT_T = solve_fixed(CAP_T, False)
            return sr, rc, rp, rf, pk, mode, adj, flex, day_def, TK, FAT_T, dc, ep
        _uf0 = sums([i for m in meals for i in m["items"]] + tr_items + snack_fixed + lunch_fixed + dinner_fixed)[2]
        def fits():
            _ex = ex_for(dc_); return _ex["f"] <= FAT_ - _uf0 - sums(rice_items(rice0))[2] and _ex["pc"] <= dc_
        _plan = [(T, lv) for T in TRC for lv in levels(T)]
        szfit = None
        for _pi, (TR, _lv) in enumerate(_plan):
            tg[0] = _lv
            sr, rc, rp, rf, pk, mode, adj, flex, day_def, TK, FAT_T, dc, ep = solve_one()
            if not TR: break
            dc_, FAT_ = dc, FAT_T
            if fits(): break
        else:
            print("WARN no dish fits", ds, TR)
        if probe and TR and ds not in TREAT and d.weekday() < 5:   # 薩莉亞放得下嗎（只記錄，不影響這次的結果）
            _sv = (TR, tg[0]); szfit = []
            for T in SZ_ROT:
                TR = T
                for _lv in levels(T):
                    tg[0] = _lv
                    _r = solve_one(); dc_, FAT_ = _r[11], _r[10]
                    if fits(): szfit.append(T); break
            TR, tg[0] = _sv
            sr, rc, rp, rf, pk, mode, adj, flex, day_def, TK, FAT_T, dc, ep = solve_one()
        assert dc >= 0, (ds, dc)
        C = fc + rc + dc
        lunch = lunch_fixed
        meals.append(dict(slot="午餐", title="麻辣燙（不加辣）配白飯", items=lunch,
                          tips=[f"午餐每天固定 {g1(LUNCH_KCAL_T)} kcal：肉片（里肌）{LUNCH_PORK_G:g} g、高麗菜 300 g（或等量青菜）放進麻辣燙，配白飯 {LUNCH_RICE_G:g} g。",
                                "炸物（豆皮、炸豆包、油條）與加工丸子、餃類少拿。",
                                "湯不要喝（湯裡有油）。"]))
        if tier == "load":
            meals.append(dict(slot="加餐（下午）", items=snack_fixed + [item("rice", sr)], tips=["肝醣超補：碳水分散到多餐，選低纖維食物。"]))
        if tr_items:
            meals.append(dict(slot=slot_tr, items=tr_items, tips=["訓練前後依實際訓練時間調整；香蕉在跑前 45 分鐘吃。"]))
        # ---- 晚餐：Meiji 1 瓶（固定）＋自由餐（剩餘預算，已扣掉這瓶 Meiji）
        used = [i for m in meals for i in m["items"]] + dinner_fixed
        uc, up, uf = sums(used)
        ex = ex_for(dc)
        leans = []   # 固定餐＋參考例蛋白質不足 130.0 g 時，參考例加里肌肉片（每 10 g），熱量從晚餐碳水扣回
        while up + ep + sum(a["p"] for a in leans) + pk < PROT_MIN_T:
            add = item("porkloin", 10)
            take = kcal_t(add["c"], add["p"], add["f"])
            assert take % 4 == 0, (ds, take)
            cg = take // 4
            if dc < cg:
                break
            dc -= cg
            FAT_T += add["f"]
            ex["p"] += add["p"]; ex["f"] += add["f"]; ex["c"] += add["c"]
            if ex.get("parts") is not None:
                ex["parts"].append(add)
            leans.append(add)
        dp = ep + sum(a["p"] for a in leans) + pk
        dfat = FAT_T - uf
        C = fc + rc + dc
        P = up + dp
        assert P >= PROT_MIN_T, (ds, g1(P))
        assert uc + dc == C and 4 * C + 4 * P + 9 * FAT_T == TK, (ds, 4 * C + 4 * P + 9 * FAT_T, TK)
        assert dc >= 0 and dfat >= 0 and dp >= 0, (ds, dc, dfat, dp)
        other_fat = max(0, dfat - ex["f"])
        def fmt_items(items, slot):
            # id：打勾紀錄用的穩定代號（餐次代號＋食物 key），不用陣列位置；同一餐重複的食物加 -2、-3
            code = SLOT_ID.get(slot, slot); seen = {}
            def iid(k):
                seen[k] = seen.get(k, 0) + 1
                kk = "chicken" if k == "porkloin" and slot.startswith("午餐") else k   # 肉片沿用舊的 lunch-chicken，已打的勾不消失
                return f"{code}-{kk}" + (f"-{seen[k]}" if seen[k] > 1 else "")
            return [dict(id=iid(i["key"]), name=i["name"], when=i["when"], amount=i["amount"], na=(["carbs", "fat"] if i["key"] == "powder" else []), carbs=g1(i["c"]), protein=g1(i["p"]), fat=g1(i["f"]),
                         kcal=g1(kcal_t(i["c"], i["p"], i["f"]))) for i in items]
        dfc, dfp, dff = sums(dinner_fixed)
        dinner = dict(fixed_items=fmt_items(dinner_fixed, "晚餐"), fixed_subtotal=dict(carbs=g1(dfc), protein=g1(dfp), fat=g1(dff), kcal=g1(kcal_t(dfc, dfp, dff))),
                      carbs=g1(dc), protein=g1(dp), fat=g1(dfat), kcal=g1(kcal_t(dc, dp, dfat)),
                      example=(dict(food=ex["name"], grams=int(float(ex["amount"].split()[0])), carbs=g1(ex["c"]), protein=g1(ex["p"]), fat=g1(ex["f"]),
                                   other_fat=g1(other_fat),
                                   text=f"{ex['name'].replace('（熟）','')} {ex['amount']}（碳水 {g1(ex['c'])} g、蛋白質 {g1(ex['p'])} g、脂肪 {g1(ex['f'])} g）" + (f"＋肉片（里肌）{sum(10 for _ in leans)} g" if leans else "") + f"＋青菜＋烹調油／醬汁／配料脂肪 {g1(other_fat)} g") if not TR else
                               dish_example(ex, dc, other_fat)),
                      tips=["晚餐喝 Meiji 1 瓶，其餘自由選，控制在上面的剩餘預算內（剩餘預算已扣掉這瓶 Meiji）。",
                            "蛋白質已由早餐、午餐與 2 瓶 Meiji 吃夠；晚餐加肉、魚或豆腐，請從脂肪預算扣。"] if not TR else
                           ["晚餐喝 Meiji 1 瓶，其餘自由選，控制在上面的剩餘預算內（剩餘預算已扣掉這瓶 Meiji）。",
                            (f"週末吃好點：本週平日晚餐共少 {g1(wk_cut(ds))} kcal，平分到週六、日（今天 +{g1(SH)} kcal）；參考例的肉／魚已算進上面的蛋白質與脂肪預算（豬排丼、鰻魚丼等也可以，控制在同樣的預算內）。" if SH > 0 else
                             "平日晚餐輪替（每週 2 天薩莉亞）：參考例的肉／魚／餐點已算進上面的蛋白質與脂肪預算；也可以換成同樣預算內的其他餐點。"
                             + (f"本週週末吃好點，今天晚餐少 {g1(-SH)} kcal（晚餐不低於 {g1(DINNER_FLOOR_T)} kcal）。" if SH < 0 else ""))]
                           + ([f"白飯／麵一餐最多 {MAX_BASE_G} g（熟重），多的碳水另列加餐。"] if ex.get("snack") else []))
        mo = []
        for m in meals:
            c, p, f = sums(m["items"])
            mo.append(dict(slot=m["slot"], title=m.get("title", ""), items=fmt_items(m["items"], m["slot"]), text_items=m.get("text_items", []),
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
            notes.append(f"長跑前一天：碳水維持 {g1(C)} g、脂肪 {g1(FLOOR_T)} g，" + (f"當天缺口 {g1(GAP)} kcal。" if GAP >= 0 else f"當天沒有缺口，比消耗多 {g1(-GAP)} kcal。"))
        if adj == "floor":
            ch = [f"晚餐碳水預算 {g1(dc)} g"]
            notes.append(f"今天目標熱量放不下碳水 {CARB_GKG[tier]} g/kg（{g1(C_TIER)} g）：脂肪已降到下限 {g1(FLOOR_T)} g（{FAT_FLOOR:.1f} g/kg），碳水減為 {g1(C)} g（" + "、".join(ch) + "）。")
        if adj == "cap":
            ch = [f"晚餐碳水預算 {g1(dc)} g"]
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
        if SH: tt = tt[:-1] + (f"；週末 +{g1(SH)}）" if SH > 0 else f"；平日 −{g1(-SH)}）")
        energy = dict(bmr=g1(BMR_T), base=g1(BASE_T), exercise=g1(EX_T), exercise_parts=ex_parts, tdee=g1(TDEE_T),
                      target=g1(TK), gap=g1(GAP), gap_t=GAP, shift=g1(SH), shift_t=SH, mode=mode, fat_adjust=adj or "", flex=flex,
                      burn_text=f"消耗 {g1(TDEE_T)} kcal（基礎代謝 {BMR:g} × {ACTIVITY:g} ＋ 運動 {g1(EX_T)}）",
                      target_text=tt)
        day = dict(date=ds, weekday="週" + WD[d.weekday()], week=ents[0]["week"], tier=tier,
                   tier_label=f"{TIER_LABEL[tier]}｜碳水 {CARB_GKG[tier]} g/kg", training=train, energy=energy,
                   targets=dict(carbs=g1(C), protein=g1(P), fat=g1(FAT_T), kcal=g1(TK),
                                protein_note=f"固定 {g1(FIXED_P)} g＋午餐高麗菜、白飯與晚餐{'參考例' if TR else '主食'}、香蕉 {g1(P - FIXED_P)} g",
                                carbs_gkg=f"{C/10/WEIGHT:.2f}", protein_gkg=f"{P/10/WEIGHT:.2f}", fat_gkg=f"{FAT_T/10/WEIGHT:.2f}",
                                carbs_reduced=adj == "floor", carbs_raised=adj == "cap"),
                   meals=mo, dinner=dinner, notes=notes, sunday=d.weekday() == 6)
        def short(m):
            if m["slot"] == "早餐" and any(i["id"] == "bf-creatine" for i in m["items"]):   # 2026-10-09：早餐行固定格式「雞蛋 2 顆＋Meiji 1 瓶＋肌酸 5 g」
                return "早餐：" + "＋".join(f"{i['name'].split('（')[0].replace(' High Protein', '')} {i['amount']}" for i in m["items"])
            parts_ = [f"{i['name'].split('（')[0]} {i['amount']}" + (f"（{i['when']}）" if i["when"] and i["when"] != m["slot"] else "") for i in m["items"]] + m.get("text_items", [])
            return f"{m['slot']}：" + (m["title"] + "（" if m["title"] else "") + "、".join(parts_) + ("）" if m["title"] else "")
        day["text"] = (f"{ds[5:].replace('-', '/')}（{day['weekday']}）飲食｜{day['tier_label']}｜{energy['burn_text']}；{energy['target_text']}｜今日：碳水 {g1(C)} g、蛋白質 {g1(P)} g、脂肪 {g1(FAT_T)} g。"
                       + "；".join([short(m) for m in mo if m["slot"] != "睡前"]
                                   + [f"晚餐：Meiji High Protein 1 瓶＋自由餐剩餘：碳水 {dinner['carbs']} g、蛋白質 {dinner['protein']} g、脂肪 {dinner['fat']} g、{dinner['kcal']} kcal（例：{dinner['example']['text']}）" + (f"；另加碳水點心：{dinner['example']['snack_text']}" if dinner['example'].get('snack_text') else "")]
                                   + [short(m) for m in mo if m["slot"] == "睡前"]) + "。"
                       + "".join(notes))
        if szfit is not None: day["_szfit"] = szfit
        out[ds] = day
        PREV_TR[0] = TR
        if ds in TREAT and TRC[0] == "漢堡王": BK_PENDING[0] = TR != "漢堡王"
        if TR in WD_ROT: WD_PTR[0] = (WD_ROT.index(TR) + 1) % len(WD_ROT)
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
               f"蛋白質：固定 {g1(FIXED_P)} g＝雞蛋 × 2（{g1(item('egg', 2)['p'])}）＋Meiji 30 g × 2 瓶（60.0；早餐、晚餐各 1 瓶）＋肉片（里肌）{LUNCH_PORK_G:g} g（{g1(item('porkloin', LUNCH_PORK_G)['p'])}）。每天至少 130.0 g（1.83 g/kg）：固定食物不夠時，晚餐參考例加里肌肉片補到 130.0 g。另加午餐高麗菜、白飯與晚餐參考例（主食、肉／魚／餐點、加餐）、香蕉的蛋白質。",
               "週末晚餐參考例輪替燒肉、牛排、漢堡王（華堡＋小薯＋零卡飲料）、牛丼、鮭魚丼，肉／魚／漢堡已算進當天晚餐剩餘（2026-10-09 起不再把平日 −100 kcal 挪到週末）；長跑前一天用鮭魚丼。半馬週 10/19–10/25 與 10K 測試週 12/21–12/27 不用週末參考例。",
               f"平日晚餐參考例輪替 {len(WD_ROT)} 道：" + "、".join(WD_ROT) + "；每週 2 個平日換成薩莉亞（肉醬義大利麵、芝麻菜雞肉沙拉、米蘭風焗飯、漢堡排、辣味烤雞中放得下當天預算的品項，碳水不夠就加點白飯）；相鄰兩天不重複（含平日與週末交界）。肉／魚／餐點已算進晚餐預算，份量依當天晚餐剩餘調整。",
               f"白飯／麵一餐最多 {MAX_BASE_G} g（熟重）；超過的碳水另列加餐（白吐司，可換成同樣碳水的香蕉、果汁或運動飲料）。10/23–10/25 晚餐維持義大利麵參考例。",
               f"脂肪：補到碳水 × 4＋蛋白質 × 4＋脂肪 × 9 剛好等於目標熱量；下限 {FAT_FLOOR:.1f} g/kg（{g1(FLOOR_T)} g）、上限 {FAT_CAP:.1f} g/kg（{g1(CAP_T)} g）。低於下限時改減碳水，高於上限時多的熱量放進碳水（晚餐；午餐固定 700.0 kcal 不調整），卡片上會註明。"],
        footnotes=[
            "基礎代謝：Mifflin MD, St Jeor ST, et al. A new predictive equation for resting energy expenditure in healthy individuals. Am J Clin Nutr 1990;51:241–247。",
            "運動 MET：Compendium of Physical Activities（Ainsworth BE et al. 2011；Herrmann SD et al. 2024 成人版）；肌力 MET 5.0、Hyrox／HIIT MET 8.0，淨消耗＝（MET − 1）× 體重 × 小時。",
            "跑步淨消耗 1 kcal/kg/km：跑步每公里的淨能量消耗與速度大致無關，約等於體重（kg）kcal（Margaria et al. 1963；ACSM Guidelines 跑步代謝公式）。",
            "每公斤體重的碳水、蛋白質、脂肪建議依據：ACSM／美國營養與飲食學會／加拿大營養師協會 2016 聯合立場聲明（Thomas et al., Med Sci Sports Exerc 48:543）與 ISSN 立場聲明（Jäger et al. 2017 蛋白質與運動；Kerksick et al. 2017 營養時機）。",
            f"午餐固定 {g1(LUNCH_KCAL_T)} kcal＝肉片（里肌，USDA FDC 168250）{LUNCH_PORK_G:g} g＋高麗菜 300 g＋白飯 {LUNCH_RICE_G:g} g；麻辣燙的湯與油沒有計入（用油每家不同），請不要喝湯。",
            "能量膠品牌未知，碳水未計入。Meiji 碳水與脂肪以巧克力口味瓶身標示計。蛋白粉於 2026-10-09 從早餐移除（太飽）。",
            "消耗是公式估算值，請以每週日的體重、體脂、腰圍趨勢檢查：連續 2 週體重沒有下降就再調整。",
            (f"活動係數 {ACTIVITY:g} 依 Pixel Watch 9/7–10/4 平均消耗 {_B['watch_calibration']['avg_4wk']} kcal／天校正（手錶會高估，未完全採用）。" if ACTIVITY != 1.2 else
             f"活動係數 {ACTIVITY:g}：2026-10-06 依你的回饋（熱量估太多）由 1.3 改回 1.2；Pixel Watch 9/7–10/4 平均消耗 {_B['watch_calibration']['avg_4wk']} kcal／天只作參考（手錶會高估）。") if _B.get("watch_calibration") else "",
        ] + ["食物數值：" + F[k]["src"] for k in ("rice", "pasta", "cabbage", "banana", "egg", "chicken", "porkloin", "meiji", "powder", "steak", "pork", "salmon", "whopper", "whopperjr", "bkfries",
                                                 "fish", "shrimp", "tomato", "ricenoodle", "eggnoodle", "bread", "sz_bolo", "sz_salad", "sz_doria", "sz_hamburg", "sz_chicken")],
    )
    return dict(meta=meta, days=out)

if __name__ == "__main__":
    import sys, os
    p = build()
    print("SHIFT_INFO", json.dumps(LAST_INFO, ensure_ascii=False))
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    json.dump(p, open(os.path.join(out, "data/diet.json"), "w"), ensure_ascii=False, indent=1)
