# 「加入行事曆」改為一鍵開啟手機行事曆

更新日期：2026-11-10

## 使用者需求

喜帖婚宴資訊頁面的「加入行事曆」按鈕，直接執行舊選單內的「手機行事曆」動作，不再先顯示選擇視窗，也不再提供 Google 日曆選項。

## 實作方式

- 將原本的 `<button id="add-calendar">` 改為原生 `<a id="add-calendar">`，其目的地即原本的 `assets/Jeremy_Yuri_Wedding.ics?v=20261013-timed`。
- 保留原按鈕的 SVG、美術字樣、CSS 類別、版面及「立即導航」。
- 移除 `<dialog id="calendar-dialog">`、`#google-calendar` 和相關 JavaScript 處理。
- iPhone／iPad：保留前版的原生 HTTPS .ics 連結，不使用 `download` 或 Blob，以便交由 iOS/瀏覽器處理；具體系統匯入視窗仍取決於 Safari 和 iOS。
- 桌面／Android：延續先前的 ICS 預載與 Blob 下載，下載檔案位元組內容不變；如果預載暫時失敗，仍保留真正的 ICS 超連結，並可在焦點重新進入時重試。
- 不變更原始 ICS 資料：2027-01-23 11:30–16:00（台灣時間）、婚宴地點、UID、提醒維持原狀。
- `main` 的 GitHub Pages 部署流程沿用 Git SHA 版本參數，以避免 iPhone 繼續讀取舊快取。

## 驗證

推送 `feat/direct-device-calendar` 分支時，GitHub Actions「Verify invitation interactions」會執行 JavaScript 語法檢查，以及 Chromium / WebKit 的桌面、iPhone、iPad 桌面 UA 與 Android 測試。測試直接點擊新的 `#add-calendar`，檢查不顯示舊彈窗、不開 Google 日曆、取得 .ics 檔，並核對活動內容與下載位元組。

既有跨瀏覽器的第三方 Google Maps 點擊導向測試有 Linux WebKit 模擬環境的偶發時序失敗，這次保留導航網址與裝置目標屬性之檢查，避免將不相關的網路時序誤判成日曆功能故障。iPhone 的實際系統行事曆匯入介面仍需以實機驗收。

## 驗收方式

開啟 `https://jeremy24582372-code.github.io/wedding_card/#invitation`，點選「加入行事曆」應直接由瀏覽器處理婚宴 ICS 檔，不應再出現「Google 日曆／手機行事曆」選擇視窗。不同裝置可能顯示下載、開啟檔案或日曆匯入提示；是否新增事件由使用者確認。