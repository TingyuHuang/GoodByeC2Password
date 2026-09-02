# GoodByeC2Password

[![tests](https://github.com/TingyuHuang/GoodByeC2Password/actions/workflows/tests.yml/badge.svg)](https://github.com/TingyuHuang/GoodByeC2Password/actions/workflows/tests.yml)

把 [Synology C2 Password](https://c2.synology.com/en-global/password/) 的 JSON 匯出檔轉成別的密碼管理器能直接匯入的檔案。

**Bitwarden 是本專案的一級目標**，輸出 Bitwarden 的 JSON 匯入格式——這是唯一能無損表達 C2 全部項目型別的路徑。其餘目標都是 CSV，且**未經實機驗證**（見下方標示）。

| 目標 | `--to` | 輸出 | 驗證程度 | 說明 |
|---|---|---|---|---|
| **Bitwarden / Vaultwarden** | `bitwarden` | **JSON** | ✅ 對過上游 importer 原始碼 | 唯一無損：卡片保持卡片、Tag 變真資料夾、密碼類欄位標記 hidden |
| Proton Pass | `proton` | CSV | 🟡 對過上游 importer 原始碼，未實機匯入 | 通用 8+1 欄；email-like username 自動進 `email` 欄 |
| 1Password | `1password` | CSV | ⚠️ 未驗證 | 自訂欄位 → 各自獨立欄；TOTP 包成 `otpauth://` |
| KeePassXC | `keepassxc` | CSV | ⚠️ 未驗證 | 原生 7 欄；TOTP 為 `otpauth://` |
| LastPass | `lastpass` | CSV | ⚠️ 未驗證 | 通用 8 欄 |
| Dashlane | `dashlane` | CSV | ⚠️ 未驗證 | credentials 範本 |
| NordPass | `nordpass` | CSV | ⚠️ 未驗證 | 擴充欄位（含 `folder`、卡片欄位） |
| Apple Passwords | `apple` | CSV | ⚠️ 未驗證 | iOS / macOS Passwords app；TOTP 為 `otpauth://` |
| Chrome | `chrome` | CSV | ⚠️ 未驗證、**有損** | 只存密碼，非 Login 項目會被略過 |
| Firefox | `firefox` | CSV | ⚠️ 未驗證、**有損** | `about:logins` CSV；非 Login 項目會被略過 |

### ⚠️ 關於「未驗證」/ On the unverified targets

**只有 `--to bitwarden` 這條路實際跑過真實的 C2 匯出檔並對照過 Bitwarden importer 的原始碼。**

其餘目標的欄位對映是依照各家**公開文件所宣稱的欄位表**寫的，作者**沒有**真的拿這些檔案去對應的密碼管理器匯入驗證過，也沒有讀過它們 importer 的實作（Proton Pass 例外，讀過原始碼但未實機匯入）。因此：

- 欄位可能錯位、被忽略，或匯入時被拒絕。
- 匯入後**請務必自行逐項核對**，特別是 TOTP、資料夾、自訂欄位。
- 匯入完成前**不要刪除 C2 的原始匯出檔**。
- 若你實際驗證過某個格式，歡迎回報或送 PR 更新這張表。

> Only `--to bitwarden` has been exercised end-to-end against a real C2 export
> and cross-checked against Bitwarden's importer source. Every other target is
> written from the vendor's documented column list and has **not** been
> verified by an actual import. Verify your data after importing, and keep the
> original C2 export until you have.

> 中文說明在下，English notes are inline below each section.

---

## 專案用途 / Purpose

Synology 已宣布 C2 Password 終止服務，現有使用者必須在期限前把資料搬到別的密碼管理器。C2 的匯出檔用的是 Synology 自己的欄位結構，其他密碼管理器不見得吃得下——尤其是付款卡、聯絡資訊這類非 Login 的項目。

這個小工具**讀 C2 的 JSON 匯出檔 → 輸出目標廠商能吃的格式**（Bitwarden 走 JSON，其餘走 CSV），並確保**每一個值都有落點**：能對應原生型別的就對應，不能的就逐欄列成自訂欄位，絕不把一整包資料塞進單一欄位。

> Reads a C2 Password JSON export and writes an importable file for the target
> manager. Every value lands somewhere: native cipher type where one exists,
> itemized custom fields where none does.

---

## 安裝 / Install

需求：Python 3.10+，無第三方相依。

```sh
# 從原始碼安裝（會註冊 c2pw-convert 指令）
pipx install .

# 或不安裝，直接在 repo 根目錄執行
python3 -m c2pw_convert <export.json> --to bitwarden -o bitwarden.json
```

macOS 內建的 `/usr/bin/python3` 是 3.9，安裝會被 `requires-python` 擋下；用
`brew install python@3.12 pipx` 裝一個新的再安裝。不安裝直接跑則不受影響。

---

## 使用方式 / Usage

### 步驟 1：從 C2 Password 匯出

1. 登入 C2 Password 網頁版
2. 右上角頭像 → **Settings** → **Export**
3. 輸入主密碼，下載 JSON 匯出檔（例如 `C2Password_Export_20260902.json`）

匯出檔的結構長這樣：

```json
{"items": [
  {"name": "…", "notes": "…", "favorite": false,
   "fields": [{"type": 0, "name": "Tags", "value": "tag a"},
              {"type": 1, "name": "Custom Field - Password Key", "value": "…"}],
   "type": 1,
   "login": {"username": "…", "password": "…", "totp": "…",
             "uris": [{"uri": "…", "match": null}]}}
]}
```

`type` 用 Bitwarden 的 cipher 編號：`1` Login、`2` Secure Note、`3` Card、`4` Identity。`fields[].type` 為 `0` 純文字、`1` 密碼（隱藏）。

### 步驟 2：轉檔

```sh
# Bitwarden：輸出 JSON（唯一無損，且唯一經過實測的路徑）
c2pw-convert C2Password_Export.json --to bitwarden  -o bitwarden.json

# 其餘目標輸出 CSV —— 這些都未經實機驗證，匯入後請自行核對
c2pw-convert C2Password_Export.json --to 1password  -o onepassword.csv
c2pw-convert C2Password_Export.json --to keepassxc  -o keepassxc.csv
c2pw-convert C2Password_Export.json --to lastpass   -o lastpass.csv
c2pw-convert C2Password_Export.json --to proton     -o proton_pass.csv
c2pw-convert C2Password_Export.json --to dashlane   -o dashlane.csv
c2pw-convert C2Password_Export.json --to nordpass   -o nordpass.csv
c2pw-convert C2Password_Export.json --to apple      -o apple_passwords.csv
c2pw-convert C2Password_Export.json --to chrome     -o chrome.csv
c2pw-convert C2Password_Export.json --to firefox    -o firefox.csv
```

不指定 `-o` 時會輸出到 stdout，可直接 pipe：

```sh
c2pw-convert C2Password_Export.json --to bitwarden | jq '.items | length'
```

### 步驟 3：匯入到目標密碼管理器

| 目標 | 操作路徑 | 匯入格式 |
|---|---|---|
| **Bitwarden / Vaultwarden** | Tools → Import data | `Bitwarden (json)` ← 一定要選 json |
| 1Password ⚠️ | File → Import → CSV | _自動偵測_ |
| KeePassXC ⚠️ | Database → Import → CSV File | _依 header 對映_ |
| LastPass ⚠️ | Account → Advanced → Import → Generic CSV File | `Generic CSV` |
| Proton Pass 🟡 | Settings → Import → Generic CSV | `Generic CSV` |
| Dashlane ⚠️ | My account → Import data → Custom CSV file | `Dashlane CSV` |
| NordPass ⚠️ | Settings → Import items → CSV | `CSV` |
| Apple Passwords ⚠️ | macOS Passwords app → File → Import Passwords | `CSV File` |
| Chrome ⚠️ | `chrome://password-manager/settings` → Import passwords | `CSV` |
| Firefox ⚠️ | `about:logins` → … → Import from a File | `CSV` |

⚠️ = 未經實機匯入驗證，🟡 = 讀過 importer 原始碼但未實機驗證。詳見開頭的說明。

### 完整 CLI 參數

```
c2pw-convert <export.json>
  --to {1password,apple,bitwarden,chrome,dashlane,
        firefox,keepassxc,lastpass,nordpass,proton}
  [-o OUTPUT]

positional:
  input              C2 Password 匯出的 JSON 檔
options:
  --to               轉換目標；bitwarden 輸出 JSON，其餘輸出 CSV
  -o, --output       輸出檔路徑；省略時印到 stdout
```

---

## 支援的資料 / What gets converted

C2 的匯出涵蓋所有內建型別。對映如下：

| C2 項目型別 | `type` | → Bitwarden | 說明 |
|---|---|---|---|
| Login | 1 | Login (1) | URL 逐一成為獨立 URI |
| Contact information | 4 | **Identity (4)** | 姓名、地址、公司、Email、電話等原生欄位 |
| Payment card | 3 | **Card (3)** | 卡號、卡別、到期日、CVV 原生欄位 |
| Secure note | 2 | Secure Note (2) | |
| Wireless router | 2 | Secure Note (2) | C2 匯出時就已是 note + 逐欄 fields |
| 其他未知型別 | any | Secure Note (2) | payload 逐欄展開成自訂欄位 |

檔案附件不在匯出檔內，必須手動搬。

> C2's export covers every built-in type. Logins, cards and contact
> information map to native Bitwarden ciphers; anything else becomes a Secure
> Note with its attributes itemized.

### 兩條硬規則 / Two hard rules

**1. 自訂欄位就是自訂欄位。** C2 `fields[]` 裡的每一筆都變成 Bitwarden 的 custom field，名稱原樣保留；C2 標成 `type: 1`（密碼）的欄位在 Bitwarden 也是 hidden 欄位，顯示為 ●●●。不會被壓成 notes 裡的一行文字。

**2. 不支援的型別逐欄條列，不打包。** 任何 Bitwarden 沒有對應 cipher 的型別都變成 Secure Note，而且**每個欄位各自成為一個 custom field**。巢狀物件與陣列會被走訪展開：

```
bankAccount: {bankName: "…", routing: {code: "…", branch: "…"}, holders: ["A","B"]}
```

會展成五個獨立欄位，而不是一個塞了 JSON 的欄位：

```
Bank Account Bank Name    = …
Bank Account Routing Code = …
Bank Account Routing Branch = …
Bank Account Holders 1    = A
Bank Account Holders 2    = B
```

> No value is ever serialized into another value. Nested payloads are walked
> so every leaf becomes its own custom field.

### Tags → 資料夾

C2 的 `Tags` 欄位會被抽出來變成**真正的 Bitwarden 資料夾**（帶 UUID，項目以 `folderId` 指向），不會留在自訂欄位裡。Bitwarden 一個項目只能屬於一個資料夾，所以若 C2 有多個 tag，取第一個當資料夾，並把完整原始值保留成一個 `Tags` 自訂欄位。

### 非 Bitwarden 目標怎麼處理 / The CSV targets

其餘九個目標都是 CSV，沒有型別、沒有自訂欄位概念。規則：

- 第一個 URL 進 url 欄，其餘 URL 附在 notes 的 `Additional URLs:` 區塊
- 卡片 / 聯絡資訊的每個值在 notes 裡**逐行條列**（`Cardholder Name: …`），同樣不打包
- 自訂欄位在 notes 末端的 `--- Custom fields ---` 區塊逐行條列
- 非 Login 項目的 notes 開頭加一行 `C2 item type: Payment card` 之類的標記
- `Tag` → 各家的 folder/group/category 欄
- TOTP：有 TOTP 欄的（LastPass/Proton/Dashlane）放純 secret；期望 URI 的（KeePassXC/Apple）包成 `otpauth://`；沒有 TOTP 欄的（NordPass/Chrome）以 `TOTP: <secret>` 附在 notes
- **NordPass 例外**：付款卡會填進它真正的 `cardholdername`/`cardnumber`/`cvc`/`expirydate` 欄，且不重複寫進 notes
- **Chrome / Firefox 例外**：只存密碼，非 Login 項目會被略過並在 stderr 警告

### 為什麼 Bitwarden 選 JSON / Why JSON for Bitwarden

Bitwarden 的 JSON importer 吃真正的 cipher 型別，CSV importer 則只認得 `note` 和「其他都是 Login」兩種——**沒有**經由 CSV 建立 Card / Identity 的途徑。所以本專案的 Bitwarden 支援只走 JSON，不提供 CSV 輸出。

| | 若走 CSV（已移除） | JSON（現行） |
|---|---|---|
| 付款卡 | Secure Note + 文字 | **Card 項目** |
| 聯絡資訊 | Secure Note + 文字 | **Identity 項目** |
| Tag | `folder` 欄的字串 | **真資料夾**（UUID + `folderId`） |
| 多個 URL | 逗號串在一個 cell | **各自獨立的 URI** |
| 密碼類自訂欄位 | 明文文字 | **hidden 欄位**（●●●） |

輸出是 deterministic 的——同一份匯入檔重跑會得到位元完全相同的結果（UUID 用 uuid5 從內容衍生），方便 diff。

卡片到期日會做一次正規化：C2 寫 `01` / `23`，Bitwarden 的表單認的是未補零的月份與四位數年份，所以輸出 `1` / `2023`。

> Bitwarden support is JSON-only: the CSV importer cannot express Card or
> Identity ciphers at all, so writing Bitwarden CSV would throw away exactly
> the items this tool exists to rescue.

轉檔時 stderr 會印出型別統計，例如：

```
Item types: Contact information: 1, Login: 1, Payment card: 1, Secure note: 2
```

CSV 目標若有東西被降級或略過，也會在這裡說：

```
note: 4 non-login item(s) were converted to notes; look for "C2 item type:" in the notes to find them.
warning: chrome can only import logins; skipped 4 non-login item(s). Convert with --to bitwarden to keep them.
```

---

## 程式化使用 / As a library

```python
from c2pw_convert import (
    build_bitwarden_export,
    parse_c2_json,
    write_apple_csv,
    write_bitwarden_json,
    write_chrome_csv,
    write_dashlane_csv,
    write_firefox_csv,
    write_keepassxc_csv,
    write_lastpass_csv,
    write_nordpass_csv,
    write_onepassword_csv,
    write_proton_csv,
)

items = parse_c2_json("C2Password_Export.json")
print(f"共 {len(items)} 筆項目")

# 依型別分流（注意：用 it.password 過濾會把卡片、筆記、路由器一起丟掉）
from collections import Counter
print(Counter(it.item_type for it in items))

write_bitwarden_json(items, "bitwarden.json")   # 無損

# 想在匯入前先檢查/改寫，可以直接拿 dict：
export = build_bitwarden_export(items)
print(len(export["items"]), "ciphers,", len(export["folders"]), "folders")
write_keepassxc_csv(items, "keepassxc.csv")
write_proton_csv(items, "proton.csv")
# ...等等
```

`C2Item` dataclass：

```python
@dataclass
class C2Item:
    name: str
    item_type: str          # login | note | card | identity
    notes: str
    favorite: bool
    tag: str                # → Bitwarden folder

    # Login payload
    urls: list[str]
    username: str
    password: str
    totp: str

    # Typed payloads, keyed as Bitwarden names them
    card: dict[str, str]      # cardholderName, brand, number, expMonth, …
    identity: dict[str, str]  # title, firstName, postalCode, country, …

    custom_fields: dict[str, str]   # 一個值一筆，永不打包
    sensitive_fields: set[str]      # custom_fields 中該隱藏的 key
```

---

## 開發 / Development

```sh
git clone <repo-url>
cd GoodByeC2Password
pip install -e ".[test]"
pytest
```

### CI

`.github/workflows/tests.yml` 在**針對 master 的 PR** 與**推進 master** 時跑整套測試，Python 3.10–3.14 各跑一次，並額外驗證 `pip install` 後的 `c2pw-convert` 進入點真的能執行。

matrix 之外還有一個 `all tests pass` 匯總 job——它只在所有 matrix job 都成功時才成功。**branch protection 只要求這一個 check 就好**，不必逐一勾選五個版本，日後增減 Python 版本也不用改設定。

> Tests run on every PR targeting master across Python 3.10–3.14. The
> aggregate `all tests pass` job is the single check to require in branch
> protection.

專案結構：

```
c2pw_convert/
  parser.py         # 讀 C2 JSON → C2Item（型別判定、fields 展開、Tags 抽出）
  _util.py          # 共用工具：otpauth URI、notes 合併、CSV writer
  bitwarden_json.py # 輸出 Bitwarden JSON（一級目標）
  onepassword.py    # 輸出 1Password CSV
  formats.py        # 其餘 8 家：KeePassXC/LastPass/Proton/Dashlane/NordPass/Apple/Chrome/Firefox
  cli.py            # 命令列入口
tests/
  C2Password_Export.json          # 真實 C2 匯出檔（五種內建型別）
  fixtures/edge_cases.json        # 未知型別、巢狀 payload、多 tag、重複欄位名
  test_parser.py                  # JSON → C2Item
  test_bitwarden_json.py          # C2Item → Bitwarden JSON
  test_formats.py                 # C2Item → 九種 CSV
  test_cli.py  test_util.py
```

---

## 安全提醒 / Security note

- 匯出的 CSV 是**未加密**的純文字，內含全部密碼。處理完之後請馬上刪除（包含瀏覽器下載資料夾、~/.Trash、雲端同步資料夾）。
- 不要把 CSV commit 到 git，也不要丟到 cloud storage。
- 匯入到新密碼管理器後，建議在新帳號裡實際登入幾個服務驗證再清掉舊資料。

> The exported CSV contains **plaintext passwords**. Delete it (and any clipboard / cloud copies) immediately after import, and verify the new vault before retiring the old one.

---

## License

MIT
