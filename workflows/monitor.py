"""
Kinki Barber Availability Monitor
Runs via GitHub Actions, sends push notifications via ntfy.sh
"""

import requests
import json
import os
import sys
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
API_URL     = "https://afspraak.kinki.nl/Datums"
PAYLOAD     = {"VestigingId": 543, "Behandelingen": ["9902"], "Stylisten": [5]}
NTFY_TOPIC  = os.environ.get("NTFY_TOPIC", "kinki-monitor")  # set in GitHub secrets
STATE_FILE  = "state.json"
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "User-Agent":   "Mozilla/5.0",
}


def fetch_dates() -> set:
    resp = requests.post(API_URL, json=PAYLOAD, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    raw = resp.json()
    if isinstance(raw, str):
        raw = json.loads(raw)
    return set(raw)


def first_available(booked: set) -> str:
    from datetime import timedelta
    today = datetime.now().date()
    check = today + timedelta(days=1)
    while check.strftime("%d-%m-%Y") in booked:
        check += timedelta(days=1)
    return check.strftime("%d-%m-%Y")


def load_state() -> set:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return None


def save_state(dates: set):
    with open(STATE_FILE, "w") as f:
        json.dump(list(dates), f)


def send_notification(title: str, message: str, priority: str = "high"):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={
                "Title":    title,
                "Priority": priority,
                "Tags":     "scissors,calendar",
            },
            timeout=10,
        )
        print(f"📲 Notification sent: {title} — {message}")
    except Exception as e:
        print(f"⚠️  Failed to send notification: {e}")


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching booked dates...")

    try:
        current = fetch_dates()
    except Exception as e:
        print(f"❌ Failed to fetch: {e}")
        sys.exit(1)

    known = load_state()

    if known is None:
        # First run — just save state
        save_state(current)
        avail = first_available(current)
        print(f"✅ First run. {len(current)} dates booked. First available: {avail}")
        send_notification(
            "Kinki Monitor started",
            f"{len(current)} dates booked. First available: {avail}",
            priority="low"
        )
        return

    gone_dates  = known - current   # dropped from booked = cancellation = bookable!
    new_dates   = current - known   # newly booked

    if gone_dates:
        sorted_free = sorted(gone_dates, key=lambda d: datetime.strptime(d, "%d-%m-%Y"))
        msg = "Slot(s) open: " + ", ".join(sorted_free)
        send_notification("🗓️ Kinki — Cancellation!", msg, priority="urgent")
    elif new_dates:
        print(f"📅 {len(new_dates)} more date(s) got booked. Total booked: {len(current)}")
    else:
        avail = first_available(current)
        print(f"✅ No change. {len(current)} booked. First available: {avail}")

    save_state(current)


if __name__ == "__main__":
    main()
