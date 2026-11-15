# Task Specification: VPS Record Creation Post-Payment & Per-User Unique VPS Naming

## 1. Context & Objective
Currently, the system creates an `Order` (`POST /api/v1/orders/purchase/`) and processes mock payment asynchronously via Celery (`process_mock_payment_task`), updating the `Order` status to `paid`. However, the corresponding `VPS` database record is not created yet, and users can currently submit duplicate VPS names.

Your task is strictly limited to:
1. Enforcing a **unique VPS name constraint per user** (at both database and validation/service layers).
2. Creating the `VPS` database record after payment succeeds, linking it to the `Order`, and updating the `Order` lifecycle accordingly.

**Out of Scope (DO NOT IMPLEMENT):**
- Do NOT implement OpenStack SDK integration (`openstacksdk`) or real cloud provider calls yet.
- Do NOT implement user VPS max-count quota limits.
- Do NOT implement VPS deletion/termination endpoints yet.

---

## 2. Existing Architecture & Models Reference
- **Primary Keys:** All models inherit from `AuditModel` (`uuid` primary key, `created_at`, `updated_at`).
- **`apps/vps/models.py` (`VPS`):**
  - Currently has: `name`, `user`, `plan`, `duration`, `ip_address`, `status` (`active`, `inactive`), `history = HistoricalRecords()`.
- **`apps/orders/models.py` (`Order`):**
  - Currently has: `user`, `plan`, `duration`, `operating_system` (optional), `vps` (OneToOneField to `vps.VPS`, nullable), `vps_name`, `cpu_snapshot`, `ram_snapshot`, `storage_snapshot`, `unit_price`, `total_amount`, `payment_method`, `payment_status`, `paid_at`, `status`.
- **`apps/orders/services.py`:** Contains `create_purchase_order(...)`.
- **`apps/orders/tasks.py`:** Contains `process_mock_payment_task(order_uuid: str)`.

---

## 3. Step-by-Step Implementation Requirements

### Step 1: Update `VPS` Model & Enforce Per-User Unique Name (`apps/vps/models.py`)
1. **Nullable `ip_address`:** Ensure `ip_address = models.GenericIPAddressField(null=True, blank=True)` so a `VPS` record can be created before IP assignment/provisioning completes.
2. **Operating System Field (if missing):** Add `operating_system = models.ForeignKey('infrastructure.OperatingSystem', on_delete=models.PROTECT, null=True, blank=True)` if `Order` tracks `operating_system`, so the `VPS` record retains its OS reference.
3. **Database-Level Unique Constraint:**
   Add a `UniqueConstraint` in `VPS.Meta` ensuring a user cannot have two VPS instances with the same `name` (case-insensitive check is recommended via `Lower('name')` or standard unique constraint on `['user', 'name']`):
   ```python
   from django.db.models import UniqueConstraint
   from django.db.models.functions import Lower

   class Meta:
       constraints = [
           UniqueConstraint(
               Lower('name'), 'user',
               name='unique_vps_name_per_user'
           )
       ]

Create and run migrations for apps/vps.

Step 2: Validate Unique VPS Name in Service Layer (apps/orders/services.py)

Update create_purchase_order before creating the Order:

    Check Existing VPS Names: Query VPS.objects.filter(user=user, name__iexact=vps_name).exists().

    Check In-Flight Pending Orders: Also check Order.objects.filter(user=user, vps_name__iexact=vps_name, status__in=['pending_payment', 'paid', 'provisioning']).exists() to prevent race conditions where two orders with the same name are submitted before the first VPS is created.

    If either exists, raise a DRF ValidationError({"vps_name": "You already have a VPS or active order with this name."}).

    Concurrency Safety: Wrap the check and Order creation inside transaction.atomic() and lock the user row via User.objects.select_for_update().get(pk=user.pk) so concurrent requests from the same user with identical vps_name cannot bypass the check.

Step 3: Create VPS Record in Mock Provisioning Flow (apps/orders/tasks.py & apps/vps/services.py)

    Update Order.status choices (apps/orders/models.py):
    Ensure status supports 'provisioning' and 'active' (e.g., pending_payment -> paid -> provisioning -> active / failed). Run migrations if choices change.

    Implement VPS Creation Helper/Service (apps/vps/services.py):
    Create a clean service function create_vps_from_order(order: Order) -> VPS:

        Must be idempotent: If order.vps is already set, return order.vps immediately.

        Inside transaction.atomic():

            Create the VPS instance using data from order:

                user=order.user

                plan=order.plan

                duration=order.duration

                operating_system=order.operating_system (if present on model)

                name=order.vps_name

                ip_address=None (or a mock private IP like '10.0.0.10' if status is set to 'active', keep status='inactive' if unprovisioned or 'active' if mock provisioning completes immediately—see below).

                status='active' (with a mock IP like '192.168.1.100' or None—use status='active' and mock IP '10.10.0.15' so the end-to-end mock flow results in a usable active VPS record, while leaving a clear # TODO: Replace mock IP/status with Infrastructure Provider comment).

            Link order.vps = vps, update order.status = 'active', and save order.

            Handle IntegrityError gracefully in case of a duplicate name race condition (mark order.status = 'failed').

    Trigger from process_mock_payment_task (apps/orders/tasks.py):

        After process_mock_payment_task marks payment_status = 'completed' and status = 'paid', either call a chained Celery task provision_vps_task.delay(str(order.uuid)) via transaction.on_commit(...) or invoke create_vps_from_order(order) inside a dedicated provision_vps_task so payment and VPS creation remain decoupled and idempotent.

Step 4: Expose VPS Info in Order Detail & Basic VPS List Endpoint

    Update OrderDetailSerializer (apps/orders/serializers.py) to include vps (e.g., vps_uuid or nested summary with uuid, name, ip_address, status) so the client sees the created VPS when polling GET /api/v1/orders/<uuid>/.

    Ensure apps/vps/ has at least a GET /api/v1/vps/ endpoint (IsAuthenticated) returning the current user's VPS list (VPS.objects.filter(user=request.user)), so the user can view their newly created VPS instances.

4. Verification Criteria

    Creating an order with a vps_name that already exists in the user's VPS table or active Orders returns HTTP 400 Bad Request.

    Two different users can use the same vps_name without conflict.

    Completing POST /api/v1/orders/purchase/ runs the Celery task(s), resulting in:

        Order having payment_status='completed', status='active', and order.vps populated.

        A new VPS record in the database belonging to request.user with the exact vps_name, plan, and duration.

    Calling GET /api/v1/vps/ returns the user's created VPS.