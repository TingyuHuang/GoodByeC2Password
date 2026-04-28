# GoodByeC2Password

把 [Synology C2 Password](https://c2.synology.com/en-global/password/) 的 CSV 匯出檔轉成主流密碼管理器都能直接匯入的 CSV。

支援的目標格式：

| 目標 | `--to` | 說明 |
|---|---|---|
| Bitwarden | `bitwarden` | 自訂欄位 → `fields` 欄 |
| 1Password | `1password` | 自訂欄位 → 各自獨立欄；TOTP 包成 `otpauth://` |
| KeePassXC | `keepassxc` | 原生 7 欄 CSV；TOTP 為 `otpauth://` |
| LastPass | `lastpass` | 通用 8 欄 CSV |
| Proton Pass | `proton` | 通用 8+1 欄 CSV；email-like username 自動進 `email` 欄 |
| Dashlane | `dashlane` | credentials 範本 CSV |
| NordPass | `nordpass` | 擴充欄位（含 `folder`） |
| Apple Passwords (iCloud Keychain) | `apple` | iOS / macOS Passwords app；TOTP 為 `otpauth://` |
| Chrome | `chrome` | 與 Chrome 自家匯出格式相同 |
| Firefox | `firefox` | `about:logins` CSV；自動補 `https://` |

> 中文說明在下，English notes are inline below each section.

---

## 專案用途 / Purpose

Synology 已宣布 C2 Password 終止服務，現有使用者必須在期限前把資料搬到別的密碼管理器。C2 提供的匯出只有一種 CSV，欄位名稱（`Display_Name`、`Login_URLs`、`Login_TOTP`…）是 Synology 自訂的，其他密碼管理器都不認得，直接匯入會失敗或欄位錯位。

這個專案就是一個小工具，**讀 C2 的 CSV → 輸出目標廠商格式的 CSV**，並處理掉幾個只有用真檔才會踩到的雷（編碼、多 URL、`Others` 是 JSON…）。

> Synology is sunsetting C2 Password. Its CSV export uses Synology-specific column names that no other manager understands. This tool reads that CSV and writes a CSV ready for Bitwarden, 1Password, KeePassXC, LastPass, Proton Pass, Dashlane, NordPass, Apple Passwords, Chrome, or Firefox.

---

## 安裝 / Install

需求：Python 3.10+，無第三方相依。

```sh
# 從原始碼安裝（會註冊 c2pw-convert 指令）
pip install .

# 或不安裝，直接執行
python -m c2pw_convert <input.csv> --to bitwarden -o out.csv
```

---

## 使用方式 / Usage

### 步驟 1：從 C2 Password 匯出 CSV

1. 登入 C2 Password 網頁版
2. 右上角頭像 → **Settings** → **Export**
3. 輸入主密碼，下載 `.csv` 檔（例如 `C2Password_export.csv`）

### 步驟 2：轉檔

```sh
# 範例：轉成各家格式
c2pw-convert C2Password_export.csv --to bitwarden  -o bitwarden.csv
c2pw-convert C2Password_export.csv --to 1password  -o onepassword.csv
c2pw-convert C2Password_export.csv --to keepassxc  -o keepassxc.csv
c2pw-convert C2Password_export.csv --to lastpass   -o lastpass.csv
c2pw-convert C2Password_export.csv --to proton     -o proton_pass.csv
c2pw-convert C2Password_export.csv --to dashlane   -o dashlane.csv
c2pw-convert C2Password_export.csv --to nordpass   -o nordpass.csv
c2pw-convert C2Password_export.csv --to apple      -o apple_passwords.csv
c2pw-convert C2Password_export.csv --to chrome     -o chrome.csv
c2pw-convert C2Password_export.csv --to firefox    -o firefox.csv
```

不指定 `-o` 時會輸出到 stdout，可直接 pipe：

```sh
c2pw-convert C2Password_export.csv --to bitwarden | less
```

### 步驟 3：匯入到目標密碼管理器

| 目標 | 操作路徑 | 匯入格式 |
|---|---|---|
| **Bitwarden** | Tools → Import data | `Bitwarden (csv)` |
| **1Password** | File → Import → CSV | _自動偵測_ |
| **KeePassXC** | Database → Import → CSV File | _依 header 對映_ |
| **LastPass** | Account → Advanced → Import → Generic CSV File | `Generic CSV` |
| **Proton Pass** | Settings → Import → Generic CSV | `Generic CSV` |
| **Dashlane** | My account → Import data → Custom CSV file | `Dashlane CSV` |
| **NordPass** | Settings → Import items → CSV | `CSV` |
| **Apple Passwords** | macOS Passwords app → File → Import Passwords | `CSV File` |
| **Chrome** | `chrome://password-manager/settings` → Import passwords | `CSV` |
| **Firefox** | `about:logins` → … → Import from a File | `CSV` |

### 完整 CLI 參數

```
c2pw-convert <input.csv>
  --to {1password,apple,bitwarden,chrome,dashlane,
        firefox,keepassxc,lastpass,nordpass,proton}
  [-o OUTPUT]

positional:
  input              C2 Password 匯出的 CSV 檔
options:
  --to               轉換目標
  -o, --output       輸出檔路徑；省略時印到 stdout
```

---

## 支援的資料 / What gets converted

C2 Password 的 CSV **只會匯出 Login 項目**。信用卡、安全筆記、身分資料、檔案附件等等都不在 CSV 裡，必須在新的密碼管理器手動建立。

> C2's export only contains Login items. Cards, secure notes, identities, and attachments are not in the CSV and must be re-entered manually.

### 共通對映規則 (其他 8 種格式)

由於 KeePassXC、LastPass、Proton Pass、Dashlane、NordPass、Apple Passwords、Chrome、Firefox 的 generic CSV importer 都只接受少數固定欄位，沒有「自訂欄位」這種概念，**每個目標格式的 writer 都遵循以下規則**：

- C2 的 `Display_Name` → 各家的 title/name 欄
- 第一個 `Login_URLs` → 各家的 url 欄；**多餘的 URL** 會以 `Additional URLs:` 區塊塞進 notes
- `Login_Username` → username 欄（Proton Pass 例外：含 `@` 時會放到 `email`）
- `Login_Password` → password 欄
- `Login_TOTP`：
  - 若目標有 TOTP 欄（LastPass/Proton/Dashlane）→ 直接放純 secret
  - 若目標期望 `otpauth://` URI（KeePassXC/Apple）→ 自動包成 `otpauth://totp/Issuer:Account?secret=...&issuer=...`
  - 若目標**沒有** TOTP 欄（NordPass/Chrome）→ 以 `TOTP: <secret>` 一行追加在 notes
- `Tag` → 各家的 folder/group/category/grouping/vault 欄
- `Notes` 與 `Others`（自訂欄位）→ 合併到 notes 欄；自訂欄位會在 notes 末端用 `--- Custom fields ---` 區塊呈現
- `Login_URL_Match_Rules`、`Tag_Color`、`Favorite`（除了 Bitwarden/1Password/LastPass 之外）→ 不保留

### 欄位對映表（Bitwarden / 1Password 細節）

| C2 Password 欄位 | → Bitwarden | → 1Password |
|---|---|---|
| `Display_Name` | `name` | `Title` |
| `Login_URLs`（多 URL 以換行分隔） | `login_uri`（逗號相連） | `Url`（第一個）+ `Additional URLs` 欄 |
| `Login_URL_Match_Rules` | _不保留_ | _不保留_ |
| `Login_Username` | `login_username` | `Username` |
| `Login_Password` | `login_password` | `Password` |
| `Login_TOTP` | `login_totp` | `OTPAuth`（包成 `otpauth://` URI） |
| `Tag` | `folder` | `Tags` |
| `Tag_Color` | _不保留_ | _不保留_ |
| `Favorite` | `favorite` | `Favorite` |
| `Notes` | `notes` | `Notes` |
| `Others`（自訂欄位） | `fields`（`name: value`） | 額外欄位（每個 key 變一欄） |

### 解析時自動處理的細節

- **編碼自動偵測**：依序嘗試 UTF-8（含 BOM）、UTF-16、CP1252、ISO-8859-1
- **多 URL cell**：C2 會把多個 URL 用換行符塞進同一個 CSV cell，這裡會 split 成陣列
- **空值正規化**：`""` / `nan` / `none` / `null` 一律當成空
- **Delimiter 偵測**：用 `csv.Sniffer` 自動判斷 `,` / `;` / Tab
- **TOTP**：C2 存的是純 secret，輸出到 1Password 時自動包成 `otpauth://totp/Issuer:Account?secret=...&issuer=Issuer`
- **`Others` 欄是 JSON**：實際的 C2 匯出把自訂欄位編成 JSON `{"Custom":[{"Type":"Text"|"Password"|"TOTP"|"Address", ...}]}`。本工具會解開並依 `Type` 萃取出 `{title: value}`；`Address` 子物件會合併成多行字串

---

## 程式化使用 / As a library

```python
from c2pw_convert import (
    parse_c2_csv,
    write_apple_csv,
    write_bitwarden_csv,
    write_chrome_csv,
    write_dashlane_csv,
    write_firefox_csv,
    write_keepassxc_csv,
    write_lastpass_csv,
    write_nordpass_csv,
    write_onepassword_csv,
    write_proton_csv,
)

items = parse_c2_csv("C2Password_export.csv")
print(f"共 {len(items)} 筆登入資料")

# 篩掉空密碼，只輸出有效項目
items = [it for it in items if it.password]

write_bitwarden_csv(items, "bitwarden.csv")
write_keepassxc_csv(items, "keepassxc.csv")
write_proton_csv(items, "proton.csv")
# ...等等
```

`C2Item` dataclass 欄位：

```python
@dataclass
class C2Item:
    name: str
    urls: list[str]
    url_match_rules: list[str]
    username: str
    password: str
    totp: str
    tag: str
    tag_color: str
    favorite: bool
    notes: str
    custom_fields: dict[str, str]
```

---

## 開發 / Development

```sh
git clone <repo-url>
cd GoodByeC2Password
pip install -e .
python -m pytest -v
```

專案結構：

```
c2pw_convert/
  parser.py         # 讀 C2 CSV，處理編碼/換行/sniffer/JSON Others
  _util.py          # 共用工具：otpauth URI、notes 合併、CSV writer
  bitwarden.py      # 輸出 Bitwarden CSV
  onepassword.py    # 輸出 1Password CSV
  formats.py        # 其餘 8 家：KeePassXC/LastPass/Proton/Dashlane/NordPass/Apple/Chrome/Firefox
  cli.py            # 命令列入口
tests/
  C2Password_Export.csv         # 真實 C2 匯出檔
  fixtures/sample_c2.csv         # 合成 fixture
  test_parser.py
  test_real_export.py
  test_formats.py
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
