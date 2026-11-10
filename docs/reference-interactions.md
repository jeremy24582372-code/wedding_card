# 原站互動比對與行動裝置修正

日期：2026-11-10

分支：`fix/reference-calendar-navigation`。尚未合併 main，也未部署此分支到正式 GitHub Pages。

## 比對依據

- 使用者提供的原站：<https://jeremy-yuri-wedding-invitation.jeremy-hsieh.chatgpt.site/#invitation>
- 原站實際讀取、按鈕點擊及導向紀錄：<https://github.com/jeremy24582372-code/wedding_card/actions/runs/42832016477>
- 修正前 main：`0fd175e2b0a563f41c85fa6176bab28fc721291e`

不是只看截圖重畫。稽核實際讀取原站 HTML、app.js、ICS，並用具有 iPhone User-Agent 與觸控設定的 Chromium 點擊三個按鈕。這是瀏覽器模擬，不是 iPhone 實機。

## 原站實際行為

| 按鈕 | 觀察到的結果 |
| --- | --- |
| 立即導航 | 原生 `<a>` 開啟 `https://www.google.com/maps/dir/?api=1&destination=...`；目的地為「晶宴日光香頌 臺北市中山區民生東路三段8號」。Google 地圖手機網頁顯示使用 App／返回網頁的選擇。原站 JavaScript 沒有自製 `confirm()` 或導航對話框。 |
| Google 日曆 | 原生連結開啟 Google Calendar 的 `action=TEMPLATE` 網址，包含活動名稱、起迄時間、說明、地點與 `Asia/Taipei` 時區。未登入的稽核環境被 Google 導向 Calendar 產品介紹頁，因此不能把未登入狀態當成已驗證的新增活動成功。 |
| 手機行事曆 | 原站預先抓取 `assets/Jeremy_Yuri_Wedding.ics?v=20261013-timed`，轉成 `text/calendar` Blob，再下載 `Jeremy_Yuri_Wedding.ics`。稽核確實觸發下載。 |

原站與修正前 main 的導航網址、日曆參數及上述互動程式相同。因此目前沒有證據能把使用者在 iPhone 看到的差異歸因於「漏複製一個確認框」。這次是針對跨站搬遷後的手機連結交接作相容性修正，而不是宣稱已在 iPhone 重現並證明唯一根因。

## 分支實作

### Google 日曆及立即導航

- 保留原站的 HTTPS 目的地及完整活動參數，不替換成其他地點、不呼叫日曆 API、不自動建立活動。
- iPhone、iPad 及 Android 使用同分頁的原生連結，避免依賴新視窗交接；桌面保留原站新分頁行為。
- 不以 `window.open()`、非同步合成點擊或假冒的 JavaScript 確認框取代真正的系統／Google 流程。
- 日曆選單在連結的原生啟動之後才關閉，而不是在 click handler 中立即隱藏被點擊的連結。

### 手機行事曆

- iPhone／iPad 改直接請求此網站上的真實 `.ics` 檔，取消強制 `download` 與 Blob URL，以便交由瀏覽器／系統的行事曆檔案處理流程接手。
- 支援 iPad 的桌面版 User-Agent；URL 以 `document.baseURI` 解析，保留 `/wedding_card/` 子目錄。
- 桌面及 Android 保留原站的一次預載、重複使用 Blob 下載行為。
- 非 iOS 的預載若暫時失敗，保留原檔案連結，下一次打開選單可重試。
- 原始 ICS 完全不修改；保留 UID、2027-01-23 11:30–16:00（台北時間）、地點與前一天提醒。沒有改成全天事件或訂閱行事曆。

### 外觀及部署

- 不修改 `index.html`、`styles.css`、圖片或日曆檔內容。
- 部署時用 Git commit SHA 更新 app.js 的版本查詢字串，避免合併後瀏覽器繼續讀舊程式。
- 測試工作流程只有讀取權限，沒有 Pages 部署權限。正式部署仍由原有 main 工作流程處理。

## 自動測試

```sh
python3 -m pip install playwright==1.56.0
python3 -m playwright install --with-deps chromium webkit
python3 tests/test_interactions.py
```

測試包含 Chromium 與 WebKit；每個引擎均測桌面、iPhone、iPad 桌面 User-Agent、Android。檢查實際 click／tap 的請求網址、是否開新視窗、返回喜帖、日曆選單、ICS 內容與日期、暫時失敗後重試。Google 目的地在回歸測試中攔截，避免存取帳號或新增任何活動；原站外部服務的實際導向另見前述稽核。

輸出 `test-results/report.json` 與各裝置截圖；GitHub Actions 保留測試產物三天。請以最新一次 workflow 結果為準，不把測試腳本存在誤當成測試通過。

## 不能由模擬器保證的部分

iPhone 的「是否開啟 Google 地圖」系統視窗、是否直接切換 App，以及行事曆原生匯入畫面，取決於 iOS、瀏覽器、App 安裝狀態及使用者過去的選擇。Linux WebKit／Chromium 無法代替實機驗證；網站也不應假冒系統提示。

目前不能聲稱使用者 iPhone 上的三個操作已逐步 100% 與原站相同。這是需實機驗收的相容性修正分支，不應在驗收前自動合併或標記完全修復。

## 合併前實機驗收

在同一支 iPhone、同一個 Safari、相同 Google 登入與 App 安裝狀態，比較原站與此分支的測試站：

1. 導航：點擊後目的地與原站一致；核對 Google 地圖／iOS 的開啟選擇，取消或返回後喜帖可正常操作。
2. Google 日曆：登入後核對新人姓名、2027-01-23 11:30–16:00、時區、地點及說明；測試不需按儲存。
3. 手機行事曆：核對系統能取得並匯入同一份 ICS，活動不是全天、時間沒有偏移、提醒相同；取消後仍能返回喜帖。
4. 分別測試手機有／沒有 Google 地圖 App，以及從 Safari、LINE 內建瀏覽器開啟。不同瀏覽器的差異應記錄，不以假對話框遮掩。

## 官方參考

- Google Maps 跨平台 URL：<https://developers.google.com/maps/documentation/urls/get-started>
- Google Maps iOS 連結與 Universal Links：<https://developers.google.com/maps/documentation/urls/ios-urlscheme>
- HTML 超連結及下載行為：<https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/a>
