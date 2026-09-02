"""CSV writers for additional password manager import formats.

Every writer here turns a list of :class:`C2Item` into the CSV layout that
the named manager's importer expects.

Common rules:

* The first URL goes into the manager's primary URL column. Any extra URLs
  are appended to the notes blob via :func:`_util.merged_notes`.
* Custom fields are folded into the notes blob too, since none of these
  managers' generic CSV importers expose typed custom fields.
* Bare TOTP secrets are wrapped into ``otpauth://`` URIs for managers whose
  import accepts URIs (KeePassXC, Apple Passwords). Managers that take a
  raw secret (LastPass, Proton Pass, Dashlane) get the secret as-is.
* C2 exports more than logins (payment cards, secure notes, wireless
  routers). Only some of these formats can express that: Proton Pass has a
  ``type`` column, NordPass has real card columns, and the rest fold
  non-login items into notes with a ``C2 item type:`` stamp on top.
  :data:`LOGIN_ONLY_WRITERS` names the two formats that cannot represent a
  non-login item at all — their importers reject rows with no URL or
  password, so those rows are skipped rather than written as garbage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, TextIO

from ._util import merged_notes, open_csv_writer, otpauth_uri, primary_url
from .parser import ITEM_TYPE_CARD, ITEM_TYPE_LOGIN, C2Item, humanize

Destination = "str | Path | TextIO"

# Formats whose importer only understands logins; see module docstring.
LOGIN_ONLY_WRITERS = frozenset({"chrome", "firefox"})


def _is_login(item: C2Item) -> bool:
    return item.item_type == ITEM_TYPE_LOGIN


# ---- KeePassXC ------------------------------------------------------------

KEEPASSXC_HEADERS = ["Group", "Title", "Username", "Password", "URL", "Notes", "TOTP"]


def write_keepassxc_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """KeePassXC's native CSV export columns. TOTP becomes an otpauth URI."""
    with open_csv_writer(destination, KEEPASSXC_HEADERS) as w:
        for it in items:
            w.writerow(
                [
                    it.tag,
                    it.name,
                    it.username,
                    it.password,
                    primary_url(it),
                    merged_notes(it),
                    otpauth_uri(it.totp, it.username, it.name),
                ]
            )


# ---- LastPass --------------------------------------------------------------

LASTPASS_HEADERS = ["url", "username", "password", "totp", "extra", "name", "grouping", "fav"]


def write_lastpass_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """LastPass generic CSV. ``extra`` holds notes, ``grouping`` holds folder.

    LastPass uses ``http://sn`` as a sentinel URL for secure-note rows; we
    fall back to it when an item has no URL so empty rows still import as
    a note rather than being rejected.
    """
    with open_csv_writer(destination, LASTPASS_HEADERS) as w:
        for it in items:
            url = primary_url(it) or "http://sn"
            w.writerow(
                [
                    url,
                    it.username,
                    it.password,
                    it.totp,
                    merged_notes(it),
                    it.name,
                    it.tag,
                    "1" if it.favorite else "0",
                ]
            )


# ---- Proton Pass -----------------------------------------------------------

PROTON_HEADERS = [
    "type", "name", "url", "email", "username", "password",
    "note", "totp", "vault",
]


def write_proton_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """Proton Pass generic CSV (8 fixed columns + vault).

    If the C2 username looks like an email we put it in the ``email`` column
    so Proton Pass shows it in the email-style field of a Login item.

    Proton's CSV reader maps ``login`` to a Login and anything it does not
    recognize to a Note, so non-login items are written as ``note``. (Its
    ``creditCard`` type expects a Proton-internal JSON blob in the note
    column, which we deliberately don't try to synthesize.)
    """
    with open_csv_writer(destination, PROTON_HEADERS) as w:
        for it in items:
            email = it.username if "@" in it.username else ""
            username = "" if email else it.username
            w.writerow(
                [
                    "login" if _is_login(it) else "note",
                    it.name,
                    primary_url(it),
                    email,
                    username,
                    it.password,
                    merged_notes(it),
                    it.totp,
                    it.tag,
                ]
            )


# ---- Dashlane --------------------------------------------------------------

DASHLANE_HEADERS = [
    "username", "username2", "username3",
    "title", "password", "note", "url", "category", "otpSecret",
]


def write_dashlane_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """Dashlane logins/credentials CSV template."""
    with open_csv_writer(destination, DASHLANE_HEADERS) as w:
        for it in items:
            w.writerow(
                [
                    it.username, "", "",
                    it.name,
                    it.password,
                    merged_notes(it),
                    primary_url(it),
                    it.tag,
                    it.totp,
                ]
            )


# ---- NordPass --------------------------------------------------------------

NORDPASS_HEADERS = [
    "name", "url", "username", "password", "note",
    "cardholdername", "cardnumber", "cvc", "expirydate", "zipcode",
    "folder", "full_name", "phone_number", "email",
    "address1", "address2", "city", "country", "state",
]


# C2 card field -> NordPass column. NordPass infers a row's item type from
# which columns are populated, so filling these makes a C2 payment card
# import as an actual card rather than as a note.
NORDPASS_CARD_COLUMNS = {
    "cardholderName": "cardholdername",
    "number": "cardnumber",
    "code": "cvc",
}


def write_nordpass_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """NordPass extended CSV: login + folder columns, plus real card columns.

    Payment cards fill ``cardholdername``/``cardnumber``/``cvc``/``expirydate``
    and are left out of the note blob so the card number isn't written twice.
    Card values with no NordPass column (the brand, a PIN kept as a custom
    field) still land in the note, one per line.
    """
    name_idx = NORDPASS_HEADERS.index("name")
    url_idx = NORDPASS_HEADERS.index("url")
    user_idx = NORDPASS_HEADERS.index("username")
    pass_idx = NORDPASS_HEADERS.index("password")
    note_idx = NORDPASS_HEADERS.index("note")
    folder_idx = NORDPASS_HEADERS.index("folder")

    with open_csv_writer(destination, NORDPASS_HEADERS) as w:
        for it in items:
            row = [""] * len(NORDPASS_HEADERS)
            row[name_idx] = it.name
            row[url_idx] = primary_url(it)
            row[user_idx] = it.username
            row[pass_idx] = it.password
            row[folder_idx] = it.tag

            mapped: set[str] = set()
            if it.item_type == ITEM_TYPE_CARD:
                for key, column in NORDPASS_CARD_COLUMNS.items():
                    value = it.card.get(key, "")
                    if value:
                        row[NORDPASS_HEADERS.index(column)] = value
                        mapped.add(humanize(key))
                expiry = "/".join(
                    v for v in (it.card.get("expMonth"), it.card.get("expYear")) if v
                )
                if expiry:
                    row[NORDPASS_HEADERS.index("expirydate")] = expiry
                    mapped.update({humanize("expMonth"), humanize("expYear")})

            note = merged_notes(it, exclude_fields=mapped)
            if it.totp:
                # NordPass generic CSV has no TOTP column; preserve in notes.
                note = (note + "\n" if note else "") + f"TOTP: {it.totp}"
            row[note_idx] = note
            w.writerow(row)


# ---- Apple Passwords (iCloud Keychain / Passwords.app) ---------------------

APPLE_HEADERS = ["Title", "URL", "Username", "Password", "Notes", "OTPAuth"]


def write_apple_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """Apple Passwords app import format. TOTP becomes an otpauth URI."""
    with open_csv_writer(destination, APPLE_HEADERS) as w:
        for it in items:
            w.writerow(
                [
                    it.name,
                    primary_url(it),
                    it.username,
                    it.password,
                    merged_notes(it),
                    otpauth_uri(it.totp, it.username, it.name),
                ]
            )


# ---- Chrome ----------------------------------------------------------------

CHROME_HEADERS = ["name", "url", "username", "password", "note"]


def write_chrome_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """Chrome's password manager CSV format (matches Chrome's own export).

    Chrome only stores passwords. Non-login C2 items have no URL and no
    password, so Chrome's importer rejects them — they are skipped here
    rather than written as rows that fail on import.
    """
    with open_csv_writer(destination, CHROME_HEADERS) as w:
        for it in items:
            if not _is_login(it):
                continue
            note = merged_notes(it)
            if it.totp:
                note = (note + "\n" if note else "") + f"TOTP: {it.totp}"
            w.writerow([it.name, primary_url(it), it.username, it.password, note])


# ---- Firefox ---------------------------------------------------------------

FIREFOX_HEADERS = [
    "url", "username", "password",
    "httpRealm", "formActionOrigin",
    "guid", "timeCreated", "timeLastUsed", "timePasswordChanged",
]


def write_firefox_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """Firefox about:logins CSV import.

    Firefox only requires ``url``/``username``/``password`` and ignores the
    rest, but it rejects rows whose URL has no scheme — we prepend
    ``https://`` to bare hostnames so the import succeeds.

    There is no notes column at all here, so non-login C2 items have nowhere
    to go and are skipped.
    """
    with open_csv_writer(destination, FIREFOX_HEADERS) as w:
        for it in items:
            if not _is_login(it):
                continue
            url = primary_url(it)
            if url and "://" not in url:
                url = "https://" + url
            w.writerow([url, it.username, it.password, "", url, "", "", "", ""])
