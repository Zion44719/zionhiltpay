"""
Mock payment gateway — simulates an external bank/card processor
(the kind of role Paystack/Flutterwave/Stripe would play in production).

This lets deposit/withdrawal flows be fully exercised end-to-end without any
real banking integration. Swap `MockPaymentGateway` for a real client later;
the interface (`initiate_deposit`, `initiate_withdrawal`) is what the rest of
the app depends on, so no callers need to change.
"""
import asyncio
import random
import secrets
from dataclasses import dataclass
from app.core.config import settings


@dataclass
class GatewayResult:
    success: bool
    gateway_reference: str
    message: str


class MockPaymentGateway:
    def __init__(self):
        self.success_rate = settings.MOCK_GATEWAY_SUCCESS_RATE
        self.latency_ms = settings.MOCK_GATEWAY_LATENCY_MS

    async def _simulate_latency(self):
        await asyncio.sleep(self.latency_ms / 1000)

    async def initiate_deposit(self, amount: float, user_reference: str) -> GatewayResult:
        await self._simulate_latency()
        gw_ref = f"MOCKGW-DEP-{secrets.token_hex(6).upper()}"
        success = random.random() <= self.success_rate
        return GatewayResult(
            success=success,
            gateway_reference=gw_ref,
            message="Deposit approved by mock gateway" if success else "Mock gateway declined the deposit (simulated)",
        )

    async def initiate_withdrawal(
        self, amount: float, bank_account_number: str, bank_code: str, user_reference: str
    ) -> GatewayResult:
        await self._simulate_latency()
        gw_ref = f"MOCKGW-WDR-{secrets.token_hex(6).upper()}"
        success = random.random() <= self.success_rate
        return GatewayResult(
            success=success,
            gateway_reference=gw_ref,
            message="Withdrawal accepted by mock gateway, settling to bank" if success
            else "Mock gateway declined the withdrawal (simulated) — funds returned to wallet",
        )


payment_gateway = MockPaymentGateway()
