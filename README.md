# GoodByeC2Password

Convert a [Synology C2 Password](https://c2.synology.com/en-global/password/pricing) CSV export into a CSV that Bitwarden or 1Password can import.

## Why

Synology announced C2 Password is being discontinued. The only export option is a CSV that uses Synology-specific column names (`Display_Name`, `Login_URLs`, `Login_TOTP`, …). Other password managers expect their own column layout, so importing the raw export fails or loses data.

## Install

```sh
pip install .
```

Or run without installing:

```sh
python -m c2pw_convert <input.csv> --to bitwarden -o out.csv
```

## Usage

```sh
# Bitwarden
c2pw-convert c2_export.csv --to bitwarden -o bitwarden.csv

# 1Password
c2pw-convert c2_export.csv --to 1password -o onepassword.csv
```

Then import the produced file:

- **Bitwarden** → Tools → Import data → format `Bitwarden (csv)`
- **1Password** → File → Import → CSV

## What the C2 Password export contains

C2's CSV export covers **only Login items**. Other item types (credit cards, secure notes, identities, attachments) must be migrated manually.

The columns observed in real exports are:

| Column | Mapped to (Bitwarden) | Mapped to (1Password) |
|---|---|---|
| `Display_Name` | `name` | `Title` |
| `Login_URLs` (newline-separated) | `login_uri` (comma-joined) | `Url` (first) + `Additional URLs` |
| `Login_URL_Match_Rules` | dropped | dropped |
| `Login_Username` | `login_username` | `Username` |
| `Login_Password` | `login_password` | `Password` |
| `Login_TOTP` | `login_totp` | `OTPAuth` (wrapped as `otpauth://`) |
| `Tag` | `folder` | `Tags` |
| `Tag_Color` | dropped | dropped |
| `Favorite` | `favorite` | `Favorite` |
| `Notes` | `notes` | `Notes` |
| `Others` (custom fields) | `fields` (`name: value`) | extra columns |

### Quirks handled by the parser
- Variable file encoding (UTF-8 with/without BOM, UTF-16, CP1252, ISO-8859-1)
- Multi-URL cells split by newline within one CSV cell
- Literal `nan` / `none` / `null` strings normalized to empty
- CSV delimiter auto-detected via `csv.Sniffer`

## Tests

```sh
python -m pytest
```
