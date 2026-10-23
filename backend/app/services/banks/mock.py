import hashlib

from app.core import nuban
from app.services.banks import AccountNotFound

# A SAMPLE list for offline use. Real deployments should use BANK_PROVIDER=paystack, which returns the live list.
SAMPLE_BANKS = [
    ("Access Bank", "044"), ("Citibank Nigeria", "023"), ("Ecobank Nigeria", "050"), ("Fidelity Bank", "070"),
    ("First Bank of Nigeria", "011"), ("First City Monument Bank", "214"), ("Guaranty Trust Bank", "058"),
    ("Heritage Bank", "030"), ("Jaiz Bank", "301"), ("Keystone Bank", "082"), ("Polaris Bank", "076"),
    ("Providus Bank", "101"), ("Stanbic IBTC Bank", "221"), ("Standard Chartered Bank", "068"),
    ("Sterling Bank", "232"), ("SunTrust Bank", "100"), ("Union Bank of Nigeria", "032"),
    ("United Bank for Africa", "033"), ("Unity Bank", "215"), ("Wema Bank", "035"), ("Zenith Bank", "057"),
    ("Kuda Microfinance Bank", "50211"), ("Moniepoint MFB", "50515"),
    ("OPay (wallet, not checkable)", "999992"), ("PalmPay (wallet, not checkable)", "999991"),
]
_SURNAMES = ["OKAFOR", "BELLO", "ADEYEMI", "IBRAHIM", "NWOSU", "ABIODUN", "EZE", "SANI", "OLADIPO", "MUSA"]
_FIRST = ["ADAEZE", "CHIDI", "TUNDE", "AMINA", "EMEKA", "FATIMA", "SEGUN", "NGOZI", "BOLA", "KELECHI"]


class MockBankProvider:
    mode = "mock"

    async def list_banks(self) -> list[dict]:
        return [{"name": n, "code": c} for n, c in SAMPLE_BANKS]

    async def resolve_account(self, bank_code: str, account_number: str) -> dict:
        names = {c: n for n, c in SAMPLE_BANKS}
        if bank_code not in names:
            raise AccountNotFound("Unknown bank")
        if account_number.startswith("999"):          # demo: accounts starting 999 don't exist
            raise AccountNotFound("Could not resolve this account")
        h = hashlib.sha256(f"{bank_code}:{account_number}".encode()).digest()
        return {
            "account_number": account_number,
            "account_name": f"{_SURNAMES[h[0] % 10]} {_FIRST[h[1] % 10]}",
            "bank_code": bank_code,
        }

    def demo_accounts(self) -> list[dict]:
        """Valid sample account numbers so the demo can be tried without knowing real ones."""
        return [
            {"bank": "Guaranty Trust Bank", "code": "058", "account_number": nuban.make_account_number("058", "000000123")},
            {"bank": "Access Bank", "code": "044", "account_number": nuban.make_account_number("044", "000000456")},
            {"bank": "Zenith Bank", "code": "057", "account_number": nuban.make_account_number("057", "000000789")},
        ]
