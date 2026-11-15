import decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.infrastructure.models import DataCenter, OperatingSystem, Region
from apps.orders.models import Order
from apps.orders.services import create_purchase_order, process_order_payment
from apps.vps.models import Duration, Plan, StatusChoices, VPS
from apps.vps.services import create_vps_from_order

User = get_user_model()


class PurchaseOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile="09120000001",
            email="buyer@example.com",
            national_id="1234567890",
            password="secret123",
        )
        self.region = Region.objects.create(name="Region A", description="A")
        self.data_center = DataCenter.objects.create(
            name="DC A",
            region=self.region,
        )
        self.other_data_center = DataCenter.objects.create(
            name="DC B",
            region=self.region,
        )
        self.plan = Plan.objects.create(
            name="Plan A",
            price="100000.00",
            description="Test plan",
            cpu=2,
            ram=4,
            storage=40,
            data_center=self.data_center,
        )
        self.duration = Duration.objects.create(
            name="1 Month",
            duration_in_month=3,
            data_center=self.data_center,
        )
        self.operating_system = OperatingSystem.objects.create(
            name="Ubuntu",
            version="22.04",
        )

    def _create_order(self, vps_name="My Test VPS", user=None):
        return create_purchase_order(
            user=user or self.user,
            plan_uuid=self.plan.uuid,
            duration_uuid=self.duration.uuid,
            operating_system_uuid=self.operating_system.uuid,
            vps_name=vps_name,
        )

    # ------------------------------------------------------------------
    # Order creation (Step A)
    # ------------------------------------------------------------------
    def test_create_purchase_order_snapshots_without_payment(self):
        order = self._create_order()

        self.assertEqual(order.cpu_snapshot, self.plan.cpu)
        self.assertEqual(order.ram_snapshot, self.plan.ram)
        self.assertEqual(order.storage_snapshot, self.plan.storage)
        self.assertEqual(order.unit_price, decimal.Decimal("100000.00"))
        self.assertEqual(order.total_amount, decimal.Decimal("300000.00"))
        self.assertEqual(order.status, "pending_payment")
        self.assertEqual(order.payment_status, "pending")
        self.assertEqual(order.vps_name, "My Test VPS")
        self.assertIsNone(order.vps_id)
        self.assertIsNone(order.payment_reference)
        self.assertEqual(VPS.objects.count(), 0)

    def test_mismatched_data_centers_raise_validation_error(self):
        duration = Duration.objects.create(
            name="1 Month",
            duration_in_month=1,
            data_center=self.other_data_center,
        )

        with self.assertRaises(ValidationError):
            create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=duration.uuid,
            )

        self.assertEqual(Order.objects.count(), 0)

    def test_inactive_plan_raises_validation_error(self):
        self.plan.is_active = False
        self.plan.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self._create_order()

        self.assertEqual(Order.objects.count(), 0)

    def test_purchase_api_returns_201_without_vps(self):
        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.post(
            "/api/v1/orders/purchase/",
            {
                "plan_uuid": str(self.plan.uuid),
                "duration_uuid": str(self.duration.uuid),
                "operating_system_uuid": str(self.operating_system.uuid),
                "vps_name": "API VPS",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["vps_name"], "API VPS")
        self.assertEqual(response.data["status"], "pending_payment")
        self.assertEqual(response.data["payment_status"], "pending")
        self.assertEqual(response.data["total_amount"], "300000.00")
        self.assertIsNone(response.data["vps"])
        self.assertEqual(VPS.objects.count(), 0)

    def test_purchase_api_mismatched_data_centers_returns_400(self):
        duration = Duration.objects.create(
            name="1 Month",
            duration_in_month=1,
            data_center=self.other_data_center,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.post(
            "/api/v1/orders/purchase/",
            {
                "plan_uuid": str(self.plan.uuid),
                "duration_uuid": str(duration.uuid),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_order_detail_only_returns_own_orders(self):
        order = self._create_order()

        other_user = User.objects.create_user(
            mobile="09120000002",
            email="other@example.com",
            national_id="0987654321",
            password="secret123",
        )
        client = APIClient()
        client.force_authenticate(user=other_user)

        response = client.get(f"/api/v1/orders/{order.uuid}/")
        self.assertEqual(response.status_code, 404)

        client.force_authenticate(user=self.user)
        response = client.get(f"/api/v1/orders/{order.uuid}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data["uuid"]), str(order.uuid))

    # ------------------------------------------------------------------
    # Per-user unique VPS name
    # ------------------------------------------------------------------
    def test_duplicate_vps_name_in_existing_vps_returns_400(self):
        VPS.objects.create(
            user=self.user,
            plan=self.plan,
            duration=self.duration,
            name="Duplicated",
            status=StatusChoices.Active,
        )

        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.post(
            "/api/v1/orders/purchase/",
            {
                "plan_uuid": str(self.plan.uuid),
                "duration_uuid": str(self.duration.uuid),
                "vps_name": "duplicated",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("vps_name", response.data)

    def test_duplicate_vps_name_in_active_order_returns_400(self):
        self._create_order(vps_name="Pending Name")

        with self.assertRaises(ValidationError):
            self._create_order(vps_name="pending name")

        self.assertEqual(Order.objects.count(), 1)

    def test_same_vps_name_allowed_for_different_users(self):
        other_user = User.objects.create_user(
            mobile="09120000003",
            email="other2@example.com",
            national_id="1112223334",
            password="secret123",
        )
        VPS.objects.create(
            user=self.user,
            plan=self.plan,
            duration=self.duration,
            name="Shared Name",
            status=StatusChoices.Active,
        )

        order = self._create_order(vps_name="Shared Name", user=other_user)

        self.assertEqual(order.vps_name, "Shared Name")

    def test_database_constraint_is_case_insensitive(self):
        VPS.objects.create(
            user=self.user,
            plan=self.plan,
            duration=self.duration,
            name="CaseSensitive",
            status=StatusChoices.Active,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VPS.objects.create(
                    user=self.user,
                    plan=self.plan,
                    duration=self.duration,
                    name="casesensitive",
                    status=StatusChoices.Active,
                )

    # ------------------------------------------------------------------
    # VPS creation helper
    # ------------------------------------------------------------------
    def test_create_vps_from_order_links_and_is_idempotent(self):
        order = self._create_order(vps_name="Provisioned VPS")

        vps = create_vps_from_order(order)
        order.refresh_from_db()

        self.assertIsNotNone(vps)
        self.assertEqual(vps.name, "Provisioned VPS")
        self.assertEqual(vps.user, self.user)
        self.assertEqual(vps.plan, self.plan)
        self.assertEqual(vps.duration, self.duration)
        self.assertEqual(vps.operating_system, self.operating_system)
        self.assertEqual(vps.status, StatusChoices.Active)
        self.assertEqual(vps.ip_address, "10.10.0.15")
        self.assertEqual(order.vps_id, vps.uuid)
        self.assertEqual(order.status, "active")

        # Second call must return the same VPS and not create another one.
        again = create_vps_from_order(order)
        self.assertEqual(again.uuid, vps.uuid)
        self.assertEqual(VPS.objects.filter(user=self.user).count(), 1)

    def test_create_vps_marks_order_failed_on_duplicate_name(self):
        order = self._create_order(vps_name="Race Name")

        # Simulate a racing request that created the VPS after the order was
        # placed but before provisioning ran.
        VPS.objects.create(
            user=self.user,
            plan=self.plan,
            duration=self.duration,
            name="Race Name",
            status=StatusChoices.Active,
        )

        result = create_vps_from_order(order)
        order.refresh_from_db()

        self.assertIsNone(result)
        self.assertEqual(order.status, "failed")
        self.assertIsNone(order.vps_id)

    # ------------------------------------------------------------------
    # Payment processing (Step B)
    # ------------------------------------------------------------------
    def test_process_order_payment_completes_and_provisions(self):
        order = self._create_order(vps_name="Paid VPS")

        paid_order, gateway_payload = process_order_payment(
            user=self.user,
            order_uuid=order.uuid,
        )

        self.assertEqual(gateway_payload["status"], "APPROVED")
        self.assertEqual(gateway_payload["gateway"], "mock_container_v1")
        self.assertTrue(
            gateway_payload["reference_id"].startswith("MOCK-PAY-")
        )

        self.assertEqual(paid_order.payment_status, "completed")
        self.assertEqual(paid_order.status, "active")
        self.assertIsNotNone(paid_order.paid_at)
        self.assertEqual(
            paid_order.payment_reference,
            gateway_payload["reference_id"],
        )
        self.assertIsNotNone(paid_order.vps_id)
        self.assertEqual(paid_order.vps.name, "Paid VPS")
        self.assertEqual(VPS.objects.filter(user=self.user).count(), 1)

    def test_pay_endpoint_returns_order_and_gateway_response(self):
        order = self._create_order(vps_name="API Paid VPS")

        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.post(f"/api/v1/orders/{order.uuid}/pay/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["order"]["status"], "active")
        self.assertEqual(
            response.data["order"]["payment_status"],
            "completed",
        )
        self.assertEqual(
            response.data["order"]["payment_reference"],
            response.data["payment_gateway_response"]["reference_id"],
        )
        self.assertEqual(
            response.data["order"]["vps"]["name"],
            "API Paid VPS",
        )
        self.assertEqual(
            response.data["payment_gateway_response"]["status"],
            "APPROVED",
        )

        # Full VPS details are also exposed as a top-level key.
        self.assertIsNotNone(response.data["vps"])
        self.assertEqual(response.data["vps"]["name"], "API Paid VPS")
        for field in (
            "uuid",
            "name",
            "ip_address",
            "status",
            "plan",
            "duration",
            "operating_system",
            "created_at",
        ):
            self.assertIn(field, response.data["vps"])
        self.assertEqual(response.data["vps"]["status"], "active")

    def test_pay_endpoint_twice_returns_400_and_no_duplicate_vps(self):
        order = self._create_order(vps_name="Double Pay VPS")

        client = APIClient()
        client.force_authenticate(user=self.user)

        first = client.post(f"/api/v1/orders/{order.uuid}/pay/")
        self.assertEqual(first.status_code, 200)

        second = client.post(f"/api/v1/orders/{order.uuid}/pay/")
        self.assertEqual(second.status_code, 400)
        self.assertIn("detail", second.data)

        self.assertEqual(VPS.objects.filter(user=self.user).count(), 1)

    def test_pay_endpoint_other_user_returns_404(self):
        order = self._create_order()

        other_user = User.objects.create_user(
            mobile="09120000005",
            email="other5@example.com",
            national_id="2223334445",
            password="secret123",
        )
        client = APIClient()
        client.force_authenticate(user=other_user)

        response = client.post(f"/api/v1/orders/{order.uuid}/pay/")

        self.assertEqual(response.status_code, 404)

    def test_pay_endpoint_non_pending_order_returns_400(self):
        order = self._create_order()
        order.status = "cancelled"
        order.save(update_fields=["status"])

        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.post(f"/api/v1/orders/{order.uuid}/pay/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.data)

    def test_gateway_failure_marks_order_failed(self):
        order = self._create_order(vps_name="Declined VPS")

        failed_order, gateway_payload = process_order_payment(
            user=self.user,
            order_uuid=order.uuid,
            simulate_failure=True,
        )

        self.assertFalse(gateway_payload["success"])
        self.assertEqual(gateway_payload["status"], "FAILED")
        self.assertTrue(
            gateway_payload["reference_id"].startswith("MOCK-FAIL-")
        )

        failed_order.refresh_from_db()
        self.assertEqual(failed_order.payment_status, "failed")
        self.assertEqual(failed_order.status, "failed")
        self.assertEqual(
            failed_order.payment_reference,
            gateway_payload["reference_id"],
        )
        self.assertIsNone(failed_order.vps_id)
        self.assertEqual(VPS.objects.count(), 0)

    def test_pay_endpoint_simulate_failure_returns_400_with_order(self):
        order = self._create_order(vps_name="API Declined VPS")

        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.post(
            f"/api/v1/orders/{order.uuid}/pay/",
            {"simulate_failure": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["payment_gateway_response"]["success"])
        self.assertEqual(
            response.data["payment_gateway_response"]["status"],
            "FAILED",
        )
        self.assertEqual(response.data["order"]["status"], "failed")
        self.assertEqual(
            response.data["order"]["payment_status"],
            "failed",
        )
        self.assertEqual(
            response.data["order"]["payment_reference"],
            response.data["payment_gateway_response"]["reference_id"],
        )
        self.assertIsNone(response.data["order"]["vps"])
        self.assertIsNone(response.data["vps"])
        self.assertEqual(VPS.objects.count(), 0)

    # ------------------------------------------------------------------
    # VPS listing
    # ------------------------------------------------------------------
    def test_vps_list_returns_only_current_user_vps(self):
        order = self._create_order(vps_name="Listed VPS")
        process_order_payment(user=self.user, order_uuid=order.uuid)

        other_user = User.objects.create_user(
            mobile="09120000004",
            email="other3@example.com",
            national_id="5556667778",
            password="secret123",
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.get("/api/v1/vps/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Listed VPS")

        client.force_authenticate(user=other_user)
        response = client.get("/api/v1/vps/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)
