# 每日更新流程（跑步儀表板）

網站：https://janjan0874-beep.github.io/running-dashboard/ ｜ Repo：`/workspace/strava/running-dashboard`（遠端 janjan0874-beep/running-dashboard，分支 main）

網站只讀 `data/*.json`，更新資料不需要改 `index.html`。
**頁面原始碼是 `/workspace/strava/index_template.html`（含手機版 RWD）；`update_dashboard.py` 每次執行會把它複製成 repo 的 `index.html`。要改版請改 template，不要直接改 repo 內的 index.html（會被覆蓋）。**

## 檔案
- `/workspace/strava/activities.csv`：單趟紀錄，欄位 `date,km,moving,pace`（日期 YYYY-MM-DD；moving 為 `m:ss` 或 `h:mm:ss`；pace 為 `m:ss`/km）。
- `/workspace/strava/monthly.csv`：月彙總 `month,runs,km,moving_time,avg_pace`。2026-07 以後由 activities.csv 重算；更早月份（無明細）保留原值。
- `/workspace/strava/profile.json`：全時間基準（`as_of` 當天為 150 次／510.9 km／232740 秒）、PR、比賽日、異常配速門檻（10:00/km）。`as_of` 之後 activities.csv 新增的跑步會自動累加進「全時間」卡片。**PR 如有刷新請手動改這裡。**
- `/workspace/strava/make_plan.py`：訓練計畫內容（逐日、假設、比賽日策略）。
- `/workspace/strava/update_dashboard.py`：主程式。

## 每日例行步驟
1. 取得新活動（Strava 匯出、API 或手動），**附加**到 `activities.csv` 末端（同日多趟各一行；已存在的日期不要重複加）。
2. 執行：
   ```bash
   cd /workspace/strava && python3 update_dashboard.py --push
   ```
   這會：重算 `monthly.csv` → 產生 `data/monthly.json、activities.json、weekly.json、summary.json、plan.json` 與 CSV 副本、`plan.md` → `git add -A` → commit（訊息含日期）→ `git push origin main`。沒有變更則略過 commit。
3. 約 1 分鐘後 GitHub Pages 自動重新部署；頁面右上角「資料更新日」會變成今天日期。
   若不想推送，省略 `--push`，再手動 `cd running-dashboard && git add -A && git commit -m ... && git push`。

## 注意
- 只需 Python 3 標準函式庫；git 使用者已在 repo 內設為 GitHub noreply；`gh` 已登入。
- 配速 >10:00/km 的月份／單趟會被標為異常（疑似步行或混合活動），圖表中壓在上限且不納入移動平均。
- 計畫已延伸到 2026-12-31（見下方「計畫階段」）。倒數與「下一個目標」由 `make_plan.py` 的 `GOALS` 與網頁自動決定：10/25（含）以前倒數半馬，10/26 起倒數 12/27 的 10K 計時測試，不需要手動換 `race_date`。
- 訓練計畫若要調整（例如受傷），直接修改 `make_plan.py` 的 `DAYS` 後重跑上面指令。

## 版面（分頁式）
- 目前是 5 分頁 app 式版面（總覽／月度／每週／配速／課表；課表分頁含 10K 測試策略與半馬賽日策略兩個折疊區），來源 `index_template.html`（layout meta：tabs-v3）；支援 `#tab=plan` 網址與 localStorage 記住分頁／區間。測試：`/workspace/pwenv/bin/python test_tabs.py 390 700`（截圖輸出 `tab_*.png`）。舊版備份：`index_template.pre_tabs.html`。

## 計畫階段（make_plan.py，10/1–12/31）
- 10/1–10/25：半馬最後 25 天（賽日 10/25，目標 1:59:46、5:40/km）。**這段內容不要改。**
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
