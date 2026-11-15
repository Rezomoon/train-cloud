import uuid
from decimal import Decimal


def charge_mock_payment(
    order_uuid: str,
    amount: Decimal,
    payment_method: str,
    simulate_failure: bool = False,
) -> dict:
    """Simulate a payment charge without any external network call."""
    if simulate_failure:
        reference_id = f"MOCK-FAIL-{uuid.uuid4().hex[:12].upper()}"
        return {
            "success": False,
            "reference_id": reference_id,
            "message": "Mock payment declined by gateway.",
            "order_uuid": str(order_uuid),
            "amount": str(amount),
            "payment_method": payment_method,
            "gateway": "mock_container_v1",
            "status": "FAILED",
        }

    reference_id = f"MOCK-PAY-{uuid.uuid4().hex[:12].upper()}"
    return {
        "success": True,
        "reference_id": reference_id,
        "message": "Mock payment processed successfully.",
        "order_uuid": str(order_uuid),
        "amount": str(amount),
        "payment_method": payment_method,
        "gateway": "mock_container_v1",
        "status": "APPROVED",
    }
