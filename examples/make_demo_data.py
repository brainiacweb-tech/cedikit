"""Generate the demo data in this folder. All names and numbers are made up.

    python examples/make_demo_data.py

* customers.csv - 500 customer phone numbers typed in many messy ways
* inbox.csv     - one month of MoMo SMS for a small trader (MTN + Telecel wallets),
                  written in the real message formats, with balances that add up
* suspicious.txt - the anonymised scam messages from the test fixtures
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

HERE = Path(__file__).parent
FIXTURES = HERE.parent / "tests" / "fixtures" / "sample_messages"
rng = random.Random(2026)

FIRST = "Kwame Kofi Kwabena Yaw Kojo Ama Akosua Abena Esi Yaa Adwoa Afia Akua Efua Nana".split()
LAST = "Mensah Owusu Asante Boateng Adjei Appiah Darko Ofori Ansah Quaye Boakye Tetteh".split()
PREFIXES = ["24", "54", "55", "59", "20", "50", "27", "26", "57"]


def name() -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def national() -> str:
    return rng.choice(PREFIXES) + "".join(str(rng.randint(0, 9)) for _ in range(7))


def messy(n: str) -> str:
    styles = [
        f"0{n}",
        f"+233{n}",
        f"233{n}",
        f"0{n[:2]} {n[2:5]} {n[5:]}",
        f"+233 {n[:2]} {n[2:5]} {n[5:]}",
        f"(0{n[:2]}) {n[2:5]}-{n[5:]}",
        f"0{n[:2]}-{n[2:5]}-{n[5:]}",
        n,
        f"00233{n}",
        f"+233 0{n}",
    ]
    return rng.choice(styles)


def customers(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "phone", "town"])
        towns = ["Kumasi", "Accra", "Tamale", "Takoradi", "Cape Coast", "Ho", "Sunyani"]
        for _ in range(500):
            n = national()
            roll = rng.random()
            if roll < 0.03:
                phone = n[:-2]  # too short
            elif roll < 0.05:
                phone = f"021{n[2:]}"  # landline
            elif roll < 0.06:
                phone = ""
            else:
                phone = messy(n)
            writer.writerow([name(), phone, rng.choice(towns)])


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class Wallets:
    def __init__(self) -> None:
        self.mtn = Decimal("210.40")
        self.telecel = Decimal("35.10")
        self.rows: list[dict[str, str]] = []
        self.ids = rng.randint(51_000_000_000, 51_900_000_000)
        self.telecel_ids = rng.randint(19_300_000_000, 19_900_000_000)

    def mtn_id(self) -> str:
        self.ids += rng.randint(3_000, 90_000)
        return str(self.ids)

    def telecel_id(self) -> str:
        self.telecel_ids += rng.randint(3_000, 90_000)
        return f"{self.telecel_ids:016d}"

    def add(self, text: str, sender: str, when: datetime) -> None:
        self.rows.append({"text": text, "sender": sender, "received_at": when.isoformat()})


def inbox(path: Path) -> None:
    w = Wallets()
    customers_ = [(name().upper(), national()) for _ in range(12)]
    agent = "ADOM MOBILE MONEY ENTERPRISE"
    supplier = "KUMASI WHOLESALE PROVISIONS"
    day = datetime(2026, 9, 1, 8, 0)
    for _ in range(30):
        day += timedelta(days=1)
        moment = day + timedelta(minutes=rng.randint(0, 40))
        for _ in range(rng.randint(1, 4)):  # customers paying by MTN MoMo
            moment += timedelta(minutes=rng.randint(20, 150))
            who, _num = rng.choice(customers_)
            amount = Decimal(rng.choice([15, 20, 25, 35, 40, 50, 60, 85, 120, 150]))
            w.mtn += amount
            w.add(
                f"Payment received for GHS {money(amount)} from {who} Current Balance: GHS "
                f"{money(w.mtn)} . Available Balance: GHS {money(w.mtn)}. Reference: "
                f"{rng.choice(['Goods', 'Rice', 'Oil', 'Provisions', 'Payment'])}. "
                f"Transaction ID: {w.mtn_id()}. TRANSACTION FEE: 0.00",
                "MobileMoney",
                moment,
            )
        if rng.random() < 0.35:  # customers paying by Telecel Cash
            moment += timedelta(minutes=rng.randint(10, 60))
            who, num = rng.choice(customers_)
            amount = Decimal(rng.choice([20, 30, 45, 70]))
            w.telecel += amount
            w.add(
                f"{w.telecel_id()} Confirmed. You have received GHS{money(amount)} from 233{num}"
                f" - {who} on {moment:%Y-%m-%d} at {moment:%H:%M:%S}. Your Telecel Cash "
                f"balance is GHS{money(w.telecel)}.\nReference: 1.\nStay alert. Never share "
                "your PIN or OTP with anyone or click unknown links. Protect your personal "
                "information.",
                "T-CASH",
                moment,
            )
        if day.weekday() == 4 and w.mtn > 300:  # Friday: restock from the supplier
            moment += timedelta(hours=1)
            amount = (w.mtn * Decimal("0.6")).quantize(Decimal("1"))
            w.mtn -= amount
            w.add(
                f"Payment for GHS{money(amount)} to {supplier} .Current Balance: GHS "
                f"{money(w.mtn)}. Transaction Id: {w.mtn_id()}. Fee charged: GHS0.00,Tax "
                "Charged 0.Download the MoMo App for a Faster & Easier Experience. Click "
                "here: https://mtnmymomo.onelink.me/XJOt/MoMo",
                "MobileMoney",
                moment,
            )
        if day.weekday() == 1 and w.mtn > 150:  # Tuesday: cash out for change
            moment += timedelta(minutes=30)
            amount = Decimal(100)
            fee = amount * Decimal("0.01")
            w.mtn -= amount + fee
            w.add(
                f"Cash Out made for GHS{money(amount)} to {agent} . Current Balance: "
                f"GHS{money(w.mtn)} Financial Transaction Id: {w.mtn_id()}. Cash-out fee is "
                "charged automatically from your MTN MoMo wallet. Please do not pay any fees "
                f"to the Agent. Thank you for using MTN MobileMoney. Fee charged: GHS{money(fee)}.",
                "MobileMoney",
                moment,
            )
        if day.day in (10, 24):  # deposit cash sales
            moment += timedelta(minutes=45)
            amount = Decimal(rng.choice([200, 250, 300]))
            w.mtn += amount
            w.add(
                f"Cash In received for GHS {money(amount)} from {agent} . Current Balance GHS "
                f"{money(w.mtn)}  Available Balance GHS {money(w.mtn)}. Transaction ID: "
                f"{w.mtn_id()}. Fee charged: GHS 0. Cash in (Deposit) is a free transaction on "
                "MTN Mobile Money. Please do not pay any fees for it.",
                "MobileMoney",
                moment,
            )
        if day.day == 28:  # monthly loan repayment
            moment += timedelta(minutes=5)
            amount = Decimal("150.00")
            w.mtn -= amount
            w.add(
                f"Payment for GHS{money(amount)} to Sika Quick Loan .Current Balance: GHS "
                f"{money(w.mtn)}. Transaction Id: {w.mtn_id()}. Fee charged: GHS0.00,Tax "
                "Charged 0.Download the MoMo App for a Faster & Easier Experience. Click "
                "here: https://mtnmymomo.onelink.me/XJOt/MoMo",
                "MobileMoney",
                moment,
            )
        if day.weekday() == 6 and w.telecel > 40:  # Sunday: airtime + send home
            moment += timedelta(hours=2)
            tx_id = w.telecel_id()
            w.telecel -= Decimal(10)
            stamp = f"on {moment:%Y-%m-%d} at {moment:%H:%M:%S}"
            w.add(
                f"{tx_id} Confirmed. You bought GHS10.00 of airtime for 233201234567 {stamp}. "
                f"Your Telecel Cash balance is GHS{money(w.telecel)}.",
                "T-CASH",
                moment,
            )
            w.add(
                f"Transaction ID: {tx_id} confirmed from 555. You have received airtime of "
                f"GHS10.00 from 233201234567 - AMA SERWAA {stamp}.",
                "T-CASH",
                moment,
            )
            amount = (w.telecel * Decimal("0.5")).quantize(Decimal("1"))
            fee = (amount * Decimal("0.005")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            w.telecel -= amount + fee
            moment += timedelta(minutes=3)
            w.add(
                f"{w.telecel_id()} Confirmed. GHS{money(amount)} sent to 0541234567 - YAA "
                f"MENSAH on MTN MOBILE MONEY on {moment:%Y-%m-%d} at {moment:%H:%M:%S}. Your "
                f"Telecel Cash balance is GHS{money(w.telecel)}. You were charged "
                f"GHS{money(fee)}. Your E-levy charge is GHS0.00. Do more with Telecel Cash! "
                "Reference: Upkeep . Sendi k3k3!",
                "T-CASH",
                moment,
            )
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["text", "sender", "received_at"])
        writer.writeheader()
        writer.writerows(w.rows)


def suspicious(path: Path) -> None:
    scams = yaml.safe_load((FIXTURES / "scam.yaml").read_text(encoding="utf-8"))
    path.write_text("\n\n".join(s["text"] for s in scams) + "\n", encoding="utf-8")


if __name__ == "__main__":
    customers(HERE / "customers.csv")
    inbox(HERE / "inbox.csv")
    suspicious(HERE / "suspicious.txt")
    print("Wrote customers.csv, inbox.csv and suspicious.txt")
