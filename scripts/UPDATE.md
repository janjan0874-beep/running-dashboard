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
- 配速 >10:00/km 的月份／單趟會被標為異常（疑似步行或混合活動），圖表中壓在上限且不納入移動平均。
- 計畫已延伸到 2026-12-31（見下方「計畫階段」）。倒數與「下一個目標」由 `make_plan.py` 的 `GOALS` 與網頁自動決定：10/25（含）以前倒數半馬，10/26 起倒數 12/27 的 10K 計時測試，不需要手動換 `race_date`。
- 訓練計畫若要調整（例如受傷），直接修改 `make_plan.py` 的 `DAYS` 後重跑上面指令。

## 版面（分頁式）
- 目前是 6 分頁 app 式版面（順序：總覽／月度／每週／配速／訓練／課表，課表在最後；課表分頁含 10K 測試策略與半馬賽日策略兩個折疊區），來源 `index_template.html`（layout meta：tabs-v4）；支援 `#tab=plan`、`#tab=train` 網址與 localStorage 記住分頁／區間。測試：`/workspace/pwenv/bin/python test_tabs.py 390 700`（手機，截圖 `tab_*.png`）與 `... test_tabs.py 1280 900`（桌面，截圖 `dtab_*.png`）；測試會檢查訓練分頁的圖表 A、B 在第一屏、無 JS 錯誤、四個範圍按鈕下 KPI 都不同。`python3 verify_train.py` 直接由 CSV 獨立重算各範圍的訓練數字，可與網頁對照。舊版備份：`index_template.pre_train.html`（5 分頁）、`index_template.pre_tabs.html`。

- **圖表提示改為圖上方讀數列（2026-10-03）**：Plotly 浮動提示框與 X 軸黑色氣泡已隱藏（CSS `.hoverlayer{display:none}` ＋ `hoverlabel` 透明），所有 `plot()` 圖與總覽迷你圖在圖正上方各有一行固定高度（18px）淡灰讀數列 `.tip`，點／滑到哪一點就顯示該點完整數值（沿用各 trace 的 `hovertemplate`，雙軸／堆疊圖併成一行），未選取顯示「點圖表查看數值」；點選後長條外其餘淡化。新增圖表只要用 `plot()`（或 `.chart` 容器＋`tipBind(id)`）並寫 `hovertemplate` 即可。測試：`/workspace/pwenv/bin/python test_tip.py 390 700`（截圖 `tip_*.png`）。舊版備份 `index_template.pre_tip.html`。

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
