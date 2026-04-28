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
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, TextIO

from ._util import merged_notes, open_csv_writer, otpauth_uri, primary_url
from .parser import C2Item

Destination = "str | Path | TextIO"


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
    """
    with open_csv_writer(destination, PROTON_HEADERS) as w:
        for it in items:
            email = it.username if "@" in it.username else ""
            username = "" if email else it.username
            w.writerow(
                [
                    "login",
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


def write_nordpass_csv(items: Iterable[C2Item], destination: Destination) -> None:
    """NordPass extended CSV. We only fill the login + folder columns."""
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
            note = merged_notes(it)
            if it.totp:
                # NordPass generic CSV has no TOTP column; preserve in notes.
                note = (note + "\n" if note else "") + f"TOTP: {it.totp}"
            row[note_idx] = note
            row[folder_idx] = it.tag
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
    """Chrome's password manager CSV format (matches Chrome's own export)."""
    with open_csv_writer(destination, CHROME_HEADERS) as w:
        for it in items:
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
    """
    with open_csv_writer(destination, FIREFOX_HEADERS) as w:
        for it in items:
            url = primary_url(it)
            if url and "://" not in url:
                url = "https://" + url
            w.writerow([url, it.username, it.password, "", url, "", "", "", ""])
