from unittest.mock import patch

import decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.infrastructure.models import DataCenter, OperatingSystem, Region
from apps.orders.models import Order
from apps.orders.services import create_purchase_order
from apps.orders.tasks import process_mock_payment_task
from apps.vps.models import Duration, Plan

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
