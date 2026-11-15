# Task Specification: Two-Step VPS Purchase & Mock Payment Endpoint Flow

## 1. Context & Objective
We are updating the VPS purchasing and billing lifecycle so that ordering and payment happen in **two distinct API steps**:
1. **Step A — Order Creation (`POST /api/v1/orders/purchase/`):** Creates an `Order` record in `pending_payment` status with `payment_status='pending'`. It must **NOT** automatically trigger payment or VPS creation upon order creation.
2. **Step B — Payment Confirmation Endpoint (`POST /api/v1/orders/<uuid:uuid>/pay/`):** When the user calls this endpoint, the service layer invokes a lightweight internal **Mock Payment Gateway Client** (simulating an external payment container/service response without real network calls). Upon receiving a successful mock response, the `Order` status transitions to `paid` (`payment_status='completed'`), and the corresponding `VPS` record is created and linked to the `Order`.

**Out of Scope (DO NOT IMPLEMENT):**
- Do NOT implement OpenStack SDK integration (`openstacksdk`) or real cloud provider calls yet.
- Do NOT implement user VPS max-count quota limits.
- Do NOT implement VPS deletion/termination endpoints yet.
- Do NOT spin up an actual separate Docker container for the payment mock; keep it as a clean, modular Python mock gateway client class inside `apps/orders/` (or `apps/orders/gateways.py`) so it can easily be swapped for a real HTTP client later.

---

## 2. Existing Architecture & Models Reference
- **Primary Keys:** All models inherit from `AuditModel` (`uuid` primary key, `created_at`, `updated_at`).
- **Authentication:** `JWTAuthentication` with `IsAuthenticated` permission on all order and VPS endpoints.
- **`apps/orders/models.py` (`Order`):**
  - `user`, `plan`, `duration`, `operating_system` (optional), `vps` (OneToOneField to `vps.VPS`, nullable), `vps_name`, `cpu_snapshot`, `ram_snapshot`, `storage_snapshot`, `unit_price`, `total_amount`, `payment_method`, `payment_status` (`pending`, `completed`, `failed`), `paid_at`, `status` (`pending_payment`, `paid`, `provisioning`, `active`, `cancelled`, `failed`), `payment_reference` (optional `CharField(max_length=100, null=True, blank=True)` to store the mock gateway transaction ID).
- **`apps/vps/models.py` (`VPS`):**
  - `name`, `user`, `plan`, `duration`, `operating_system` (optional), `ip_address` (`null=True, blank=True`), `status` (`active`, `inactive`), `history = HistoricalRecords()`.

---

## 3. Step-by-Step Implementation Requirements

### Step 1: Enforce Per-User Unique VPS Name & Update Models
1. **`apps/vps/models.py`:**
   - Ensure `ip_address = models.GenericIPAddressField(null=True, blank=True)`.
   - Add a case-insensitive database-level `UniqueConstraint` on `(Lower('name'), 'user')` named `'unique_vps_name_per_user'` so a user cannot have duplicate VPS names.
2. **`apps/orders/models.py`:**
   - Add `payment_reference = models.CharField(max_length=100, null=True, blank=True)` to store the mock payment gateway reference/tracking ID returned during payment.
   - Ensure `status` choices include `'pending_payment'`, `'paid'`, `'active'`, `'cancelled'`, and `'failed'`.
   - Create and run migrations if any model fields/constraints were added or changed.

---

### Step 2: Decouple Order Creation (`apps/orders/services.py` -> `create_purchase_order`)
Modify `create_purchase_order`:
1. **Remove Automatic Payment Trigger:** Remove any `transaction.on_commit(...)` call that automatically triggered `process_mock_payment_task` upon order creation. The order must remain in `status='pending_payment'` and `payment_status='pending'` until the user explicitly calls the pay endpoint.
2. **Unique VPS Name Validation (Concurrency-Safe):**
   - Inside `with transaction.atomic():`, lock the user row via `User.objects.select_for_update().get(pk=user.pk)`.
   - Check if a `VPS` with `user=user` and `name__iexact=vps_name` already exists.
   - Check if an active/in-progress `Order` with `user=user`, `vps_name__iexact=vps_name`, and `status__in=['pending_payment', 'paid', 'provisioning', 'active']` already exists.
   - If either exists, raise DRF `ValidationError({"vps_name": "You already have a VPS or active order with this name."})`.
3. **Price & Snapshot Integrity:** Keep server-side calculation (`total_amount = plan.price * duration.duration_in_month`), `Plan.is_active` check, and `plan.data_center_id == duration.data_center_id` check.

---

### Step 3: Mock Payment Gateway Client (`apps/orders/gateways.py`)
Create a clean, isolated mock client `MockPaymentGatewayClient` that simulates calling an external payment container/service and returning structured mock response data:
```python
import uuid
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class PaymentGatewayResponse:
    success: bool
    reference_id: str
    message: str
    raw_payload: dict

class MockPaymentGatewayClient:
    """Simulates sending a payment request to an external payment service/container."""

    def charge(self, order_uuid: str, amount: Decimal, payment_method: str) -> PaymentGatewayResponse:
        mock_ref = f"MOCK-PAY-{uuid.uuid4().hex[:12].upper()}"
        return PaymentGatewayResponse(
            success=True,
            reference_id=mock_ref,
            message="Mock payment processed successfully.",
            raw_payload={
                "order_uuid": str(order_uuid),
                "amount": str(amount),
                "payment_method": payment_method,
                "gateway": "mock_container_v1",
                "status": "APPROVED",
                "reference_id": mock_ref,
            },
        )


        Step 4: Payment Processing & VPS Creation Service (apps/orders/services.py & apps/vps/services.py)

    VPS Creation Helper (apps/vps/services.py -> create_vps_from_order(order: Order) -> VPS):

        Idempotent: If order.vps is already not None, return order.vps immediately.

        Create the VPS record using order attributes (user=order.user, plan=order.plan, duration=order.duration, operating_system=order.operating_system if present, name=order.vps_name, ip_address='10.10.0.15' as mock IP, status='active', with a # TODO: Replace mock IP/status with Infrastructure Provider comment).

        Link order.vps = vps and set order.status = 'active'.

    Order Payment Service (apps/orders/services.py -> process_order_payment(user, order_uuid)):

        Inside with transaction.atomic()::

            Fetch the order with Order.objects.select_for_update().get(uuid=order_uuid, user=user) (raise DRF NotFound if not found).

            State & Idempotency Validation:

                If order.payment_status == 'completed' or order.status in ['paid', 'active'], either return the existing order idempotently or raise ValidationError({"detail": "This order has already been paid."}) (raising ValidationError on duplicate pay requests is recommended for explicit API feedback).

                If order.status != 'pending_payment', raise ValidationError({"detail": f"Cannot pay for an order in '{order.status}' status."}).

            Call Mock Gateway: Call gateway_response = MockPaymentGatewayClient().charge(order.uuid, order.total_amount, order.payment_method).

            Handle Response:

                If gateway_response.success is True:

                    Update order.payment_status = 'completed'

                    Update order.status = 'paid'

                    Update order.paid_at = timezone.now()

                    Update order.payment_reference = gateway_response.reference_id

                    Save order

                    Immediately call create_vps_from_order(order) (or trigger via Celery if preferred, ensuring the VPS record is created and linked so order.status becomes 'active' and order.vps is populated).

                If gateway_response.success is False:

                    Update order.payment_status = 'failed', order.status = 'failed', save order, and raise ValidationError({"detail": gateway_response.message}).

        Return (order, gateway_response.raw_payload).

Step 5: API Endpoints & Serializers (apps/orders/views.py, serializers.py, urls.py)

    Update OrderDetailSerializer (apps/orders/serializers.py):

        Include payment_reference and a read-only representation of vps (uuid, name, ip_address, status, or None when unpaid).

    Add PayOrderAPIView (POST /api/v1/orders/<uuid:uuid>/pay/):

        permission_classes = [IsAuthenticated]

        Calls process_order_payment(user=request.user, order_uuid=uuid).

        Returns HTTP 200 OK with the serialized OrderDetailSerializer data and the gateway_response payload (e.g., {"order": ..., "payment_gateway_response": ...}).

    Wire URL in apps/orders/urls.py:

        Add path('<uuid:uuid>/pay/', PayOrderAPIView.as_view(), name='order-pay').

    Ensure GET /api/v1/vps/ exists (apps/vps/views.py & urls.py):

        Returns the authenticated user's VPS instances (VPS.objects.filter(user=request.user)).

4. Verification Criteria

    Calling POST /api/v1/orders/purchase/ creates an Order with status='pending_payment', payment_status='pending', and vps=None. No VPS record exists yet.

    Calling POST /api/v1/orders/purchase/ again with the same vps_name for the same user returns HTTP 400 Bad Request.

    Calling POST /api/v1/orders/<uuid>/pay/ invokes MockPaymentGatewayClient, updates payment_status='completed', sets paid_at and payment_reference, creates the VPS record in the database, links order.vps, and sets order.status='active'.

    Calling POST /api/v1/orders/<uuid>/pay/ a second time on the same order returns HTTP 400 Bad Request without creating a duplicate VPS.

    Calling GET /api/v1/vps/ returns the newly created VPS for the authenticated user.