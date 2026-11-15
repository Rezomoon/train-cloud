from unittest.mock import patch

import decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.infrastructure.models import DataCenter, OperatingSystem, Region
from apps.orders.models import Order
from apps.orders.services import create_purchase_order
from apps.orders.tasks import process_mock_payment_task, provision_vps_task
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

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_create_purchase_order_snapshots_and_enqueues(self, delay_mock):
        with self.captureOnCommitCallbacks(execute=True):
            order = create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
                operating_system_uuid=self.operating_system.uuid,
                vps_name="My Test VPS",
            )

        self.assertEqual(order.cpu_snapshot, self.plan.cpu)
        self.assertEqual(order.ram_snapshot, self.plan.ram)
        self.assertEqual(order.storage_snapshot, self.plan.storage)
        self.assertEqual(order.unit_price, decimal.Decimal("100000.00"))
        self.assertEqual(order.total_amount, decimal.Decimal("300000.00"))
        self.assertEqual(order.status, "pending_payment")
        self.assertEqual(order.payment_status, "pending")
        self.assertEqual(order.vps_name, "My Test VPS")
        delay_mock.assert_called_once_with(str(order.uuid))

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

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_inactive_plan_raises_validation_error(self, delay_mock):
        self.plan.is_active = False
        self.plan.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
            )

        delay_mock.assert_not_called()

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_mock_payment_task_is_idempotent(self, delay_mock):
        with self.captureOnCommitCallbacks(execute=True):
            order = create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
            )

        process_mock_payment_task(str(order.uuid))
        order.refresh_from_db()

        self.assertEqual(order.payment_status, "completed")
        self.assertEqual(order.status, "paid")
        self.assertIsNotNone(order.paid_at)
        paid_at = order.paid_at

        # Running the task a second time must not change anything.
        process_mock_payment_task(str(order.uuid))
        order.refresh_from_db()

        self.assertEqual(order.payment_status, "completed")
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.paid_at, paid_at)

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_purchase_api_returns_201(self, delay_mock):
        client = APIClient()
        client.force_authenticate(user=self.user)

        with self.captureOnCommitCallbacks(execute=True):
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
        delay_mock.assert_called_once()

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

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_order_detail_only_returns_own_orders(self, delay_mock):
        with self.captureOnCommitCallbacks(execute=True):
            order = create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
            )

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

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_duplicate_vps_name_in_existing_vps_returns_400(self, delay_mock):
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
        delay_mock.assert_not_called()

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_duplicate_vps_name_in_active_order_returns_400(self, delay_mock):
        with self.captureOnCommitCallbacks(execute=True):
            create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
                vps_name="Pending Name",
            )

        with self.assertRaises(ValidationError):
            create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
                vps_name="pending name",
            )

        self.assertEqual(Order.objects.count(), 1)

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_same_vps_name_allowed_for_different_users(self, delay_mock):
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

        with self.captureOnCommitCallbacks(execute=True):
            order = create_purchase_order(
                user=other_user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
                vps_name="Shared Name",
            )

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

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_create_vps_from_order_links_and_is_idempotent(self, delay_mock):
        with self.captureOnCommitCallbacks(execute=True):
            order = create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
                operating_system_uuid=self.operating_system.uuid,
                vps_name="Provisioned VPS",
            )

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

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_create_vps_marks_order_failed_on_duplicate_name(self, delay_mock):
        with self.captureOnCommitCallbacks(execute=True):
            order = create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
                vps_name="Race Name",
            )

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

    @patch("apps.orders.services.process_mock_payment_task.delay")
    @patch("apps.orders.tasks.provision_vps_task.delay")
    def test_full_payment_and_provisioning_flow(
        self,
        provision_delay,
        payment_delay,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order = create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
                vps_name="End To End",
            )

        with self.captureOnCommitCallbacks(execute=True):
            process_mock_payment_task(str(order.uuid))

        provision_delay.assert_called_once_with(str(order.uuid))

        # Run the decoupled provisioning task synchronously.
        provision_vps_task(str(order.uuid))
        order.refresh_from_db()

        self.assertEqual(order.payment_status, "completed")
        self.assertEqual(order.status, "active")
        self.assertIsNotNone(order.vps_id)
        self.assertEqual(order.vps.name, "End To End")

    @patch("apps.orders.services.process_mock_payment_task.delay")
    def test_vps_list_returns_only_current_user_vps(self, delay_mock):
        with self.captureOnCommitCallbacks(execute=True):
            order = create_purchase_order(
                user=self.user,
                plan_uuid=self.plan.uuid,
                duration_uuid=self.duration.uuid,
                vps_name="Listed VPS",
            )
        create_vps_from_order(order)

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
