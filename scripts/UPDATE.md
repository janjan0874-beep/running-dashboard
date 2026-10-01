# 每日更新流程（跑步儀表板）

網站：https://janjan0874-beep.github.io/running-dashboard/ ｜ Repo：`/workspace/strava/running-dashboard`（遠端 janjan0874-beep/running-dashboard，分支 main）

網站只讀 `data/*.json`，更新資料不需要改 `index.html`。

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
- 比賽日（2026-10-25）過後可把 `profile.json` 的 `race_date` 與 `make_plan.py` 的內容換成新目標。
- 訓練計畫若要調整（例如受傷），直接修改 `make_plan.py` 的 `DAYS` 後重跑上面指令。
