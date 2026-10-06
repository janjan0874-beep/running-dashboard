# 每日更新流程（跑步儀表板）

網站：https://janjan0874-beep.github.io/running-dashboard/ ｜ Repo：`/workspace/strava/running-dashboard`（遠端 janjan0874-beep/running-dashboard，分支 main）

網站只讀 `data/*.json`，更新資料不需要改 `index.html`。
**頁面原始碼是 `/workspace/strava/index_template.html`（含手機版 RWD）；`update_dashboard.py` 每次執行會把它複製成 repo 的 `index.html`。要改版請改 template，不要直接改 repo 內的 index.html（會被覆蓋）。**

## 檔案
- `/workspace/strava/activities.csv`：單趟紀錄，欄位 `date,km,moving,pace`（日期 YYYY-MM-DD；moving 為 `m:ss` 或 `h:mm:ss`；pace 為 `m:ss`/km）。
- `/workspace/strava/monthly.csv`：月彙總 `month,runs,km,moving_time,avg_pace`。2026-07 以後由 activities.csv 重算；更早月份（無明細）保留原值。
- `/workspace/strava/workouts.csv`：非跑步活動（Workout／HIIT／Swim／Stair-Stepper…），欄位 `date,start_time,name,type,elapsed,moving,avg_hr,max_hr,calories,distance_km,url`（elapsed／moving 為 `h:mm:ss`；沒有心率的活動 avg_hr、max_hr 留空）。**去重以 `url` 為鍵**。
- `/workspace/strava/profile.json`：全時間基準（`as_of` 當天為 150 次／510.9 km／232740 秒）、PR、比賽日、異常配速門檻（10:00/km）。`as_of` 之後 activities.csv 新增的跑步會自動累加進「全時間」卡片。**PR 如有刷新請手動改這裡。**
- `/workspace/strava/make_plan.py`：訓練計畫內容（逐日、假設、比賽日策略）。
- `/workspace/strava/make_diet.py`：飲食計畫（讀 `make_plan.build()` 的逐日訓練產生，課表一改飲食自動同步）→ `data/diet.json`。
- `/workspace/strava/update_dashboard.py`：主程式。

## 每日例行步驟
1. 取得新活動（Strava 匯出、API 或手動），**附加**到 `activities.csv` 末端（同日多趟各一行；已存在的日期不要重複加）。
1b. **非跑步活動**（Workout、HIIT、Swim、Stair-Stepper…）附加到 `workouts.csv`（欄位如上）。新增前先檢查 `url` 是否已存在（`grep -c <activity id> workouts.csv`）；程式讀檔時也會以 `url` 去重（保留第一筆、略過其餘並印出筆數），但仍請不要重複加。日期不必排序，程式會依日期＋開始時間排序。
2. 執行：
   ```bash
   cd /workspace/strava && python3 update_dashboard.py --push
   ```
   這會：重算 `monthly.csv` → 產生 `data/monthly.json、activities.json、weekly.json、summary.json、workouts.json、plan.json` 與 CSV 副本（含 `workouts.csv`）、`plan.md` → `git add -A` → commit（訊息含日期）→ `git push origin main`。沒有變更則略過 commit。
3. 約 1 分鐘後 GitHub Pages 自動重新部署；頁面右上角「資料更新日」會變成今天日期。
   若不想推送，省略 `--push`，再手動 `cd running-dashboard && git add -A && git commit -m ... && git push`。

## 注意
- 只需 Python 3 標準函式庫；git 使用者已在 repo 內設為 GitHub noreply；`gh` 已登入。
- 配速 >10:00/km（`profile.json` 的 `pace_outlier_threshold_min`）的月份／單趟在 JSON 中標 `outlier: true`（每次執行 `update_dashboard.py` 依門檻重算，新資料自動套用）。**配速分頁完全不顯示這些點**（2026-10-06 使用者要求「配速異常點直接拿掉、看乾淨的趨勢」）：不畫點、無 ✕／異常圖例，也不納入平均配速、7 趟移動平均（單趟）與 3 個月移動平均（每月）；移動平均以全部歷史計算再切到範圍（單趟不足 3 趟不畫），Y 軸只依保留的點決定範圍（`paceAxis()`）。這些跑步**仍計入跑量、次數、時數**等距離／時間統計。目前排除的單趟：07/13 1.05 km 11:13、07/19 1.70 km 11:49、08/01 1.47 km 16:41、08/01 0.69 km 11:06、08/27 0.72 km 11:03；月份：2025-07（18:48）、2025-08（10:58）、2025-12（18:29）。要改門檻請改 `profile.json`。備份 `index_template.pre_paceclean.html`、`UPDATE.pre_paceclean.md`。
- 計畫已延伸到 2026-12-31（見下方「計畫階段」）。倒數與「下一個目標」由 `make_plan.py` 的 `GOALS` 與網頁自動決定：10/25（含）以前倒數半馬，10/26 起倒數 12/27 的 10K 計時測試，不需要手動換 `race_date`。
- 訓練計畫若要調整（例如受傷），直接修改 `make_plan.py` 的 `DAYS` 後重跑上面指令。

## 版面（分頁式）
- 目前是 7 分頁 app 式版面（順序：總覽／月度／每週／配速／訓練／課表／飲食，2026-10-06 新增飲食分頁；課表分頁含 10K 測試策略與半馬賽日策略兩個折疊區），來源 `index_template.html`（layout meta：tabs-v4）；支援 `#tab=plan`、`#tab=train` 網址與 localStorage 記住分頁／區間。測試：`/workspace/pwenv/bin/python test_tabs.py 390 700`（手機，截圖 `tab_*.png`）與 `... test_tabs.py 1280 900`（桌面，截圖 `dtab_*.png`）；測試會檢查訓練分頁的圖表 A、B 在第一屏、無 JS 錯誤、四個範圍按鈕下 KPI 都不同。`python3 verify_train.py` 直接由 CSV 獨立重算各範圍的訓練數字，可與網頁對照。舊版備份：`index_template.pre_train.html`（5 分頁）、`index_template.pre_tabs.html`。

- **圖表提示改為圖上方讀數列（2026-10-03）**：Plotly 浮動提示框與 X 軸黑色氣泡已隱藏（CSS `.hoverlayer{display:none}` ＋ `hoverlabel` 透明），所有 `plot()` 圖與總覽迷你圖在圖正上方各有一行固定高度（18px）淡灰讀數列 `.tip`，點／滑到哪一點就顯示該點完整數值（沿用各 trace 的 `hovertemplate`，雙軸／堆疊圖併成一行），未選取顯示「點圖表查看數值」；點選後長條外其餘淡化。新增圖表只要用 `plot()`（或 `.chart` 容器＋`tipBind(id)`）並寫 `hovertemplate` 即可。測試：`/workspace/pwenv/bin/python test_tip.py 390 700`（截圖 `tip_*.png`）。舊版備份 `index_template.pre_tip.html`。
- **點長條標亮修正（2026-10-06）**：點選長條時，標亮的那一根改用「點到的 x 值」在各長條 trace 中找索引（原本用 `e.points[0].pointNumber`，hovermode 'x' 時第一個點可能是 4 週滾動平均折線，其陣列從第 4 週才開始，造成每週圖標亮偏移 3 根）。測試：`/workspace/pwenv/bin/python test_barclick.py 390 700`（逐圖點長條中心，斷言讀數列與標亮都是同一根；自帶 8768 埠伺服器）。備份 `index_template.pre_barsel.html`。
- 8765 埠若被其他程式占用，`test_tabs.py` 可自行起伺服器後帶第三個參數網址：`python3 -m http.server 8767 -d _site &` → `test_tabs.py 390 700 http://localhost:8767/index.html`。

## 「訓練」分頁（第 5 分頁，啞鈴圖示）
- 資料來源：`workouts.csv` → `data/workouts.json`（`rows` 逐筆、`weekly` 週一起算的每週彙總、`monthly` 每月彙總；全部是整數次／整數秒，網頁只做加總）。
- **Workout 定義**：type＝Workout 或 HIIT（肌力／Hyrox 類；HIIT 目前只有 1 筆，2025-06-21，會在卡片註明）。Swim、Stair-Stepper **不算 Workout**，只列入圖 B 的「其他」時數。Workout 時間一律用 elapsed；沒有紀錄的欄位（如 Swim 缺心率）不計入平均。
- 範圍按鈕（與其他分頁相同：以日曆月計、含資料截止月）：A 圖與 KPI 從範圍起始月 1 日之後的第一個週一算到最新資料日；「至今」從第一筆 Workout 所在週的週一算起。**達標＝完整週（週一至週日都已過）內 Workout ≥ 2 次**；本週進行中以淡色顯示，不計入達標週數與「平均每週次數」（＝完整週內次數 ÷ 完整週數）。目標 2 次／週來自使用者的肌力計畫（肩、背、腿），要改請改 `update_dashboard.py` 的 `target_per_week` 輸出（`build_workouts`）。
- 5 張 KPI 卡：Workout 次數、總時數、平均每週次數、平均心率（各次平均心率的算術平均，只算有心率的次數）、總熱量（Workout 的 Cal 加總）。
- 圖 A 每週 Workout 次數＋目標線；圖 B 整體運動時數（跑步＋Workout＋其他）：近 3 個月用週（都在跑步明細期間內），其餘用月；**跑步時數＝moving time，2026-07-03（activities.csv 最早日）前只有月彙總，所以不能拆到週**，且跑步資料只到 activities.csv 最後一天，之後沒有紀錄就不計；圖 C 平均心率（折線）與熱量（長條，同 B 的週／月單位）；下方是最近 5 次 Workout（不受範圍影響）。
- 手機版 390×700 的第一屏要同時看到 KPI、圖 A、圖 B（圖 C 與表格在下方）；`.chart.tr` 高度由 `100svh` 推算，改版後務必跑 `test_tabs.py 390 700`（程式會斷言 A、B 圖的底邊在分頁列之上）。

## 計畫階段（make_plan.py，10/1–12/31）
- 10/1–10/25：半馬最後 25 天（賽日 10/25，目標 1:59:46、5:40/km）。10/4 已依使用者要求最佳化 10/5–10/24（備份 make_plan.pre_opt.py），之後除非使用者要求不要再動。
- 10/26–11/1：賽後恢復（10/26 完全休息，之後只輕鬆跑＋輕量肌力），週跑量 15.0 km（後續遞增的起點）。
- 11/2–11/29：基礎期（strides、輕鬆長跑、節奏跑），週跑量 16.5、18.1、19.9、17.9（減量週）km。
- 11/30–12/27：10K 專項期（5×1 km @5:00 間歇、節奏跑 @5:20、3 km @5:00 模擬），週跑量 19.6、21.5、22.0、20.5（減量＋測試週）km。
- 12/20：5 km 測試，全程 4:42/km（12.8 km/h）。門檻 23:30。
- **12/27（週日）：下一個目標。10K 計時測試，目標 49:59 以內（全程 4:58/km、12.1 km/h）。** 12/20 的 5 km 超過 23:30，就把 12/27 目標改為 51:00（5:06/km，11.8 km/h）：改 `make_plan.py` 中 12/27 的 note、`TEST_PLAN`、`CAVEAT`、`ASSUMPTIONS`、`GOALS` 對應文字。
- 12/28–12/31：休息、輕量肌力、輕鬆跑；12/31 做最終回報（體脂 15% 目標）。
- 每週日請使用者回報體重、體脂、腰圍、疲勞度（1–5 分）。肌力每週 2 次，每週 1 天完全休息。

## 修改計畫的規則（每日 8:00 例行流程適用）
- 所有數字必須是單一明確數字：配速、跑步機速度、距離都不能用區間，不寫「約」「大概」「左右」。（日期範圍與 1–5 分疲勞量表除外。）
- 週跑量必須等於逐日加總：改任何一天的 km，同步改 `WEEK_TOTAL`；`build()` 會用 assert 檢查週總量、每週增幅不超過前週 10%、每週 2 次肌力與 1 天休息，不符就會報錯。
- km/h = 60 ÷ 每公里分鐘數，四捨五入到 0.1；新增配速請用 `tm("m:ss")` 產生跑步機速度。
- 每次跑步都要有跑步機版本（0% 坡度）。腳癢發作就停。
- 實際跑步資料仍附加到 `activities.csv`；計畫要依實際狀況（受傷、疲勞）調整時，只改今天之後的日子。
- 檢查：`python3 update_dashboard.py` → `/workspace/pwenv/bin/python test_tabs.py 390 700` → 確認再 `--push`。

## 「飲食」分頁（第 7 分頁，刀叉圖示；2026-10-06 新增）
- 來源：`make_diet.py` → `data/diet.json`（`update_dashboard.py` 每次執行都會重產，每日 8:00 例行流程不需額外步驟）。範圍 2026-10-06～2026-12-31。
- **diet.json 格式**：`{"meta": {...}, "days": {"YYYY-MM-DD": {...}}}`。每日訊息直接引用 `days["2026-10-06"]["text"]`（一段完整繁中摘要：當日目標、早餐、午餐、訓練前後、晚餐剩餘預算＋參考、睡前、週日提醒）。其他欄位：`tier`／`tier_label`、`training`、`targets`（carbs／protein／fat／kcal 字串，0.1 精度）、`meals[]`（slot、items[name, when, amount, carbs, protein, fat, kcal]、subtotal、tips）、`dinner`（剩餘預算＋example）、`notes`、`sunday`。
- 使用者資料在 `profile.json` 的 `body`（176 cm、32 歲、男、71 kg、體脂 17.5%、目標 15%）；體重變了改這裡即可。
- **熱量（2026-10-06 起）**：BMR＝Mifflin-St Jeor 10×71＋6.25×176−5×32＋5＝1655；消耗（TDEE）＝1655×1.2＋課表運動（跑步 71 kcal/km×公里；肌力（MET 5.0−1）×71×小時，時間取課表 note 的「N 分鐘」，沒寫算 45 分鐘；Hyrox／HIIT 用 MET 8.0；休息 0）。目標＝TDEE−183；10/23、10/24、10/25 吃到維持（`MAINTENANCE`）。卡片顯示「消耗 X kcal（基礎代謝 1655 × 1.2 ＋ 運動 Y）」「目標 X kcal（−183）」與運動明細。
- **巨量營養素**：碳水照分級、蛋白質照固定基礎＋食物；脂肪補到 4C＋4P＋9F 剛好等於目標（0.1 kcal 尾數由晚餐蛋白質預算吸收，最多 0.4 g）。脂肪下限 0.6 g/kg＝42.6 g：低於下限時脂肪定在下限，改減碳水（晚餐預算先減；晚餐碳水比午餐白飯少 28 g 以上時改減午餐白飯 10 g；超補日也減加餐白飯），卡片 notes 會寫「碳水減為 X g（午餐白飯 A → B g…）」，`targets.carbs_reduced=true`。
- 目前（10/6 計算）87 天中有 52 天碰到脂肪下限而減碳水（休息日、肌力日、短輕鬆跑日、長跑前一天、10/23–10/24 超補日）；長跑日脂肪會變高（10/11 74.2 g；10/25 比賽日 150.5 g）。這是使用者規則的直接結果，要改規則請改 `make_diet.py` 的 `MAINTENANCE`、`FAT_FLOOR`、`CARB_GKG`。
- 碳水分級（`classify()`）：肝醣超補 10/23、10/24 → 8 g/kg（568 g；10/6 起受維持熱量與脂肪下限限制）；kind=race（10/25 半馬、12/27 10K）→ 5 g/kg；課表類型含「長跑」且 ≥10 km → 長跑日 5 g/kg（10 km 以下的輕鬆長跑算輕鬆跑日 4 g/kg）；含 節奏／間歇／目標配速／測試／配速模擬 → 強度課日 5 g/kg；隔天跑 ≥14 km → 長跑前一天 5 g/kg；其他跑步日 4 g/kg；肌力日、休息日 3 g/kg。同一天有多項時取最高級。
- 蛋白質＝固定 138.6 g（Meiji 30 g×2、蛋白粉 35 g、雞蛋 2 顆 12.6 g、雞胸肉 100 g 31.0 g）＋白飯／義大利麵／地瓜／香蕉的蛋白質。脂肪依目標熱量計算（見上，下限 42.6 g）。熱量＝4/4/9。
- 餐次：早餐固定（蛋白粉＋雞蛋 2 顆＋瓜瓜園地瓜，地瓜 100／120／150／180 g 依分級：休息與肌力／輕鬆跑／5 g/kg 日／超補；2026-10-06 使用者改為不吃燕麥，備份 `make_diet.pre_sweetpotato.py`）；午餐固定麻辣燙（不加辣）＋雞胸肉 100 g＋白飯（白飯克數＝剩餘碳水的一半，取 10 g 整數；超補日分三份含下午加餐）；訓練前後：跑步日香蕉 1 根（跑前 45 分鐘）＋Meiji（訓練後），跑步＋肌力同日兩瓶分別在跑後、肌力後；非訓練日 Meiji 為下午點心；不足 2 瓶的補在睡前；晚餐自由＝當日目標扣掉其他餐的剩餘預算，參考例休息／肌力日用白飯、其他日用義大利麵。10/25 早餐（起跑前 3 小時）碳水 142 g＋比賽中能量膠 × 2（品牌未知，碳水不計）。
- 食物數值（USDA FDC，已核對）：白飯 28.2/2.7/0.3（168878）、義大利麵 30.9/5.8/0.9（SR 20121）、瓜瓜園地瓜用瓜瓜園冰烤地瓜包裝營養標示 35.9/1.1/0.2（每 100 g；Pure17Go 350 g 與優統食品 1 kg 零售頁轉載的包裝標示，兩者相同；官網未公開文字標示）、香蕉中型 118 g 27.0/1.3/0.4（173944）、雞蛋大顆水煮 0.6/6.3/5.3（173424）、雞胸肉熟 0/31.0/3.6（171477）；Meiji 蛋白質 30.0（使用者提供）、碳水 9.8、脂肪 2.1（巧克力口味瓶身）；蛋白粉只計蛋白質 35.0（網頁顯示「—」）。
- `build()` 內有 assert：各餐加總＋晚餐預算必須剛好等於當日碳水，且 4C＋4P＋9F 必須剛好等於目標熱量（十分之一 kcal），晚餐碳水／蛋白質／脂肪預算不可為負。備份：`make_diet.pre_tdee.py`、`profile.pre_tdee.json`、`index_template.pre_tdee.html`、`UPDATE.pre_tdee.md`。
- 測試：`test_tabs.py` 已加入飲食分頁檢查（今天卡片 ≥3 個餐表、晚餐預算、週卡片、7 個分頁都在 390px 內）；截圖 `/workspace/pwenv/bin/python shot_diet.py [網址] [前綴]` → `diet_390x700.png`、`diet_full.png`。備份：`index_template.pre_diet.html`、`update_dashboard.pre_diet.py`、`UPDATE.pre_diet.md`、`test_tabs.pre_diet.py`。
