# گزارش پیاده‌سازی خرید VPS و پرداخت آزمایشی (Mock Payment)

## ۱. خلاصه

طبق فایل `docs/purchase_vps_task.md`، فرایند **ایجاد سفارش خرید VPS** و **پردازش غیرهمزمان پرداخت آزمایشی** پیاده‌سازی شد. موارد خارج از محدوده (OpenStack، ساخت واقعی VPS، سقف تعداد VPS و مدل `Transaction`) وارد نشدند.

خروجی نهایی:

- مدل `Order` بازطراحی شد و مدل `Transaction` وجود ندارد و هیچ ارجاعی به آن باقی نمانده است.
- منطق کسب‌وکار در لایه سرویس (`services.py`) قرار گرفت.
- تسک Celery برای پرداخت آزمایشی با قفل همزمانی و محافظ Idempotency اضافه شد.
- سریالایزرها، ویوها و مسیرهای API اضافه شدند.
- پیکربندی Celery و Redis انجام شد.
- مایگریشن ساخته و اعمال شد.
- ۷ تست خودکار نوشته و با موفقیت اجرا شد.

---

## ۲. فایل‌های ایجادشده و تغییرکرده

| فایل | وضعیت | توضیح |
|---|---|---|
| `cloud_project/apps/orders/models.py` | بازنویسی | مدل جدید `Order` و حذف `Transaction` |
| `cloud_project/apps/orders/services.py` | ایجاد | تابع `create_purchase_order` |
| `cloud_project/apps/orders/tasks.py` | ایجاد | تسک `process_mock_payment_task` |
| `cloud_project/apps/orders/serializers.py` | ایجاد | `PurchaseVPSInputSerializer` و `OrderDetailSerializer` |
| `cloud_project/apps/orders/views.py` | بازنویسی | `PurchaseVPSAPIView` و `OrderDetailAPIView` |
| `cloud_project/apps/orders/urls.py` | ایجاد | مسیرهای `purchase/` و `<uuid:uuid>/` |
| `cloud_project/apps/orders/admin.py` | به‌روزرسانی | نمایش فیلدهای جدید در پنل ادمین |
| `cloud_project/apps/orders/migrations/0002_refactor_order_model.py` | ایجاد | مایگریشن تغییرات مدل |
| `cloud_project/apps/orders/tests.py` | بازنویسی | تست‌های سرویس، تسک و API |
| `cloud_project/cloud_project/celery.py` | ایجاد | نمونه Celery |
| `cloud_project/cloud_project/__init__.py` | به‌روزرسانی | بارگذاری Celery همراه پروژه |
| `cloud_project/cloud_project/settings.py` | به‌روزرسانی | تنظیمات Redis/Celery |
| `cloud_project/cloud_project/urls.py` | به‌روزرسانی | ثبت `api/v1/orders/` |
| `requirements.txt` | به‌روزرسانی | افزودن `celery` و `redis` |
| `docker-compose.yaml` | به‌روزرسانی | افزودن سرویس Redis |
| `cloud_project/.envs/.env.example` | به‌روزرسانی | متغیرهای Celery |

---

## ۳. مدل `Order`

مدل جدید از `AuditModel` ارث‌بری می‌کند؛ بنابراین `uuid`، `created_at` و `updated_at` به‌صورت خودکار دارد.

### ۳-۱. روابط

```python
user = models.ForeignKey(
    "users.User",
    on_delete=models.CASCADE,
    related_name="orders",
)
plan = models.ForeignKey("vps.Plan", on_delete=models.PROTECT)
duration = models.ForeignKey("vps.Duration", on_delete=models.PROTECT)
operating_system = models.ForeignKey(
    "infrastructure.OperatingSystem",
    on_delete=models.PROTECT,
    null=True,
    blank=True,
)
vps = models.OneToOneField(
    "vps.VPS",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="order",
)
```

- `operating_system` اختیاری/Nullable است تا انتخاب سیستم‌عامل اجباری نباشد.
- `vps` از نوع `OneToOneField` و Nullable است، چون VPS بعد از پرداخت ساخته می‌شود.

### ۳-۲. فیلدهای Snapshot

```python
vps_name = models.CharField(max_length=100, default="My VPS")
cpu_snapshot = models.IntegerField()
ram_snapshot = models.IntegerField()
storage_snapshot = models.IntegerField()
unit_price = models.DecimalField(max_digits=10, decimal_places=2)
```

این مقادیر در زمان خرید از روی `Plan` کپی می‌شوند تا تغییرات بعدی پلن، سفارش تاریخی را تغییر ندهد.

### ۳-۳. فیلدهای پرداخت و چرخه عمر

```python
total_amount = models.DecimalField(max_digits=10, decimal_places=2)
payment_method = models.CharField(
    max_length=50,
    choices=PaymentMethodChoices.choices,
    default=PaymentMethodChoices.BANK,
)
payment_status = models.CharField(
    max_length=50,
    choices=PaymentStatusChoices.choices,
    default=PaymentStatusChoices.PENDING,
)
paid_at = models.DateTimeField(null=True, blank=True)
status = models.CharField(
    max_length=50,
    choices=OrderStatusChoices.choices,
    default=OrderStatusChoices.PENDING_PAYMENT,
)
```

مقادیر مجاز:

- `payment_method`: `wallet`، `bank`
- `payment_status`: `pending`، `completed`، `failed`
- `status`: `pending_payment`، `paid`، `cancelled`، `failed`

---

## ۴. لایه سرویس (`services.py`)

تابع `create_purchase_order` مسئول کل منطق کسب‌وکار است و ویوها هیچ محاسبه‌ای انجام نمی‌دهند.

### ۴-۱. ورودی‌ها

```python
def create_purchase_order(
    user,
    plan_uuid,
    duration_uuid,
    operating_system_uuid=None,
    vps_name=None,
    payment_method=PaymentMethodChoices.BANK,
):
```

### ۴-۲. اعتبارسنجی‌ها

1. پلن باید وجود داشته باشد و `is_active=True` باشد.
2. مدت‌زمان باید وجود داشته باشد.
3. `plan.data_center_id` باید با `duration.data_center_id` برابر باشد.
4. اگر `operating_system_uuid` ارسال شده باشد، سیستم‌عامل باید وجود داشته باشد و `is_active=True` باشد.
5. در صورت خطا، `rest_framework.exceptions.ValidationError` پرتاب می‌شود که خروجی آن HTTP 400 است.

### ۴-۳. محاسبه قیمت در سمت سرور

```python
total_amount = plan.price * duration.duration_in_month
```

هیچ مبلغی از سمت کلاینت پذیرفته نمی‌شود.

### ۴-۴. ساخت اتمیک و ارسال تسک بعد از Commit

```python
with transaction.atomic():
    order = Order.objects.create(
        user=user,
        plan=plan,
        duration=duration,
        operating_system=operating_system,
        vps_name=vps_name or "My VPS",
        cpu_snapshot=plan.cpu,
        ram_snapshot=plan.ram,
        storage_snapshot=plan.storage,
        unit_price=plan.price,
        total_amount=total_amount,
        payment_method=payment_method,
        payment_status=PaymentStatusChoices.PENDING,
        status=OrderStatusChoices.PENDING_PAYMENT,
    )

    transaction.on_commit(
        lambda: process_mock_payment_task.delay(str(order.uuid))
    )
```

استفاده از `transaction.on_commit` تضمین می‌کند تسک فقط بعد از Commit شدن واقعی سفارش اجرا شود؛ در نتیجه Worker همیشه رکورد سفارش را پیدا می‌کند.

---

## ۵. تسک Celery (`tasks.py`)

```python
@shared_task
def process_mock_payment_task(order_uuid: str):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(uuid=order_uuid)

        if (
            order.payment_status == PaymentStatusChoices.COMPLETED
            or order.status != OrderStatusChoices.PENDING_PAYMENT
        ):
            return

        order.payment_status = PaymentStatusChoices.COMPLETED
        order.status = OrderStatusChoices.PAID
        order.paid_at = timezone.now()
        order.save(
            update_fields=[
                "payment_status",
                "status",
                "paid_at",
                "updated_at",
            ]
        )

        # TODO: Trigger VPS provisioning task here
```

نکات مهم:

- **قفل همزمانی:** `select_for_update()` از پردازش همزمان دو تسک روی یک سفارش جلوگیری می‌کند.
- **Idempotency:** اگر سفارش قبلاً پرداخت شده باشد یا وضعیت آن `pending_payment` نباشد، تسک بدون تغییر داده خارج می‌شود.
- **بدون درخواست خارجی:** هیچ فراخوانی HTTP به درگاه پرداخت انجام نمی‌شود.
- **TODO:** محل اتصال تسک ساخت VPS برای فاز بعدی مشخص شده است.

---

## ۶. سریالایزرها

### ۶-۱. `PurchaseVPSInputSerializer`

```python
class PurchaseVPSInputSerializer(serializers.Serializer):
    plan_uuid = serializers.UUIDField(required=True)
    duration_uuid = serializers.UUIDField(required=True)
    operating_system_uuid = serializers.UUIDField(required=False)
    vps_name = serializers.CharField(
        required=False,
        default="My VPS",
        max_length=100,
    )
    payment_method = serializers.ChoiceField(
        choices=PaymentMethodChoices.choices,
        required=False,
        default=PaymentMethodChoices.BANK,
    )
```

### ۶-۲. `OrderDetailSerializer`

فیلدهای خروجی: `uuid`، `vps_name`، `plan`، `duration`، `cpu_snapshot`، `ram_snapshot`، `storage_snapshot`، `unit_price`، `total_amount`، `payment_method`، `payment_status`، `status`، `paid_at`، `created_at`.

سریالایزر فقط خواندنی است و `plan` و `duration` به‌صورت UUID برگردانده می‌شوند.

---

## ۷. ویوها و مسیرها

### ۷-۱. `PurchaseVPSAPIView`

- مسیر: `POST /api/v1/orders/purchase/`
- دسترسی: `IsAuthenticated`
- ورودی را با `PurchaseVPSInputSerializer` اعتبارسنجی می‌کند.
- تابع `create_purchase_order` را صدا می‌زند.
- خروجی `OrderDetailSerializer` با وضعیت `201 Created` برمی‌گرداند.

### ۷-۲. `OrderDetailAPIView`

- مسیر: `GET /api/v1/orders/<uuid:uuid>/`
- دسترسی: `IsAuthenticated`
- فقط سفارش‌های همان کاربر را برمی‌گرداند (`user=request.user`).
- سفارش کاربر دیگر یا UUID ناموجود، `404` می‌دهد.

### ۷-۳. مسیرها

`apps/orders/urls.py`:

```python
urlpatterns = [
    path("purchase/", PurchaseVPSAPIView.as_view(), name="order-purchase"),
    path("<uuid:uuid>/", OrderDetailAPIView.as_view(), name="order-detail"),
]
```

`cloud_project/urls.py`:

```python
path("api/v1/orders/", include("apps.orders.urls")),
```

---

## ۸. پیکربندی Celery و Redis

### ۸-۱. `cloud_project/celery.py`

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cloud_project.settings")

app = Celery("cloud_project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

### ۸-۲. `cloud_project/__init__.py`

```python
from .celery import app as celery_app

__all__ = ("celery_app",)
```

### ۸-۳. تنظیمات `settings.py`

```python
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env(
    'CELERY_RESULT_BACKEND', default='redis://localhost:6379/0'
)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
```

### ۸-۴. وابستگی‌ها

در `requirements.txt`:

```text
celery==5.4.0
redis==5.0.8
```

### ۸-۵. Redis در Docker Compose

سرویس `redis` با ایمیج `redis:7-alpine` و پورت `6379` اضافه شد.

---

## ۹. مایگریشن

مایگریشن `apps/orders/migrations/0002_refactor_order_model.py` ساخته و اعمال شد.

تغییرات آن:

- حذف `resource_price` و `amount`
- تغییر `vps` به `OneToOneField` با `SET_NULL`
- تغییر `on_delete` پلن و مدت‌زمان به `PROTECT`
- افزودن `operating_system`، `vps_name`، `cpu_snapshot`، `ram_snapshot`، `storage_snapshot`، `unit_price`، `total_amount`، `payment_status` و `paid_at`
- به‌روزرسانی `choices` و `default` فیلدهای `status` و `payment_method`
- افزودن `related_name="orders"` به کاربر

برای رکوردهای قبلی، مقادیر موقت `0` برای فیلدهای عددی در مایگریشن در نظر گرفته شد و سپس default حذف شد (`preserve_default=False`).

---

## ۱۰. تست‌ها

فایل `apps/orders/tests.py` شامل ۷ تست است:

1. ساخت سفارش با پلن/مدت معتبر و بررسی Snapshotها و مبلغ نهایی.
2. ارسال تسک بعد از Commit با UUID صحیح سفارش.
3. خطای 400 برای عدم تطابق DataCenter پلن و مدت.
4. خطای 400 برای پلن غیرفعال.
5. Idempotency تسک پرداخت (اجرای دوباره تغییری ایجاد نمی‌کند).
6. پاسخ `201 Created` از `POST /api/v1/orders/purchase/`.
7. عدم دسترسی به سفارش کاربر دیگر (`404`) و دسترسی به سفارش خود (`200`).

نتیجه اجرا:

```text
Found 7 test(s).
System check identified no issues (0 silenced).
.......
Ran 7 tests in 3.434s

OK
```

همچنین:

```text
manage.py check            -> no issues
makemigrations --check     -> No changes detected
```

---

## ۱۱. نحوه اجرا

از پوشه `cloud_project`:

```bash
# ۱. اجرای PostgreSQL و Redis
docker compose up -d

# ۲. اعمال مایگریشن‌ها
../.venv/bin/python manage.py migrate

# ۳. اجرای سرور
../.venv/bin/python manage.py runserver

# ۴. اجرای Worker در ترمینال جداگانه
../.venv/bin/celery -A cloud_project worker -l info
```

اجرای تست‌ها:

```bash
../.venv/bin/python manage.py test apps.orders
```

---

## ۱۲. نمونه فراخوانی API

### ۱۲-۱. خرید

```bash
curl -X POST http://localhost:8000/api/v1/orders/purchase/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_uuid": "<PLAN_UUID>",
    "duration_uuid": "<DURATION_UUID>",
    "operating_system_uuid": "<OS_UUID>",
    "vps_name": "My VPS",
    "payment_method": "bank"
  }'
```

پاسخ `201 Created`:

```json
{
  "uuid": "...",
  "vps_name": "My VPS",
  "plan": "...",
  "duration": "...",
  "cpu_snapshot": 2,
  "ram_snapshot": 4,
  "storage_snapshot": 40,
  "unit_price": "100000.00",
  "total_amount": "300000.00",
  "payment_method": "bank",
  "payment_status": "pending",
  "status": "pending_payment",
  "paid_at": null,
  "created_at": "..."
}
```

### ۱۲-۲. بررسی وضعیت سفارش

```bash
curl http://localhost:8000/api/v1/orders/<ORDER_UUID>/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

پس از اجرای تسک، مقادیر `payment_status` برابر `completed`، `status` برابر `paid` و `paid_at` مقداردار خواهد بود.

---

## ۱۳. تطابق با معیارهای پذیرش

| معیار | وضعیت |
|---|---|
| عدم وجود مدل/ارجاع `Transaction` | ✅ هیچ ارجاعی وجود ندارد |
| ساخت سفارش با Snapshot صحیح و پاسخ 201 | ✅ تست شده |
| ارسال تسک با `transaction.on_commit` | ✅ تست شده |
| خطای 400 برای عدم تطابق DataCenter | ✅ تست شده |
| به‌روزرسانی پرداخت و Idempotency تسک | ✅ تست شده |
| حذف مدل `Transaction` | ✅ (از قبل وجود نداشت) |

---

## ۱۴. تصمیم‌های فنی

- `operating_system` به‌صورت Nullable پیاده شد، چون در مشخصات «اختیاری» ذکر شده بود.
- `plan` و `duration` در خروجی به‌صورت UUID نمایش داده می‌شوند تا پاسخ سبک بماند و از N+1 Query جلوگیری شود.
- برای جلوگیری از خطای مایگریشن روی داده‌های موجود، فیلدهای غیرNullable جدید ابتدا با default موقت ساخته و سپس default آن‌ها حذف شد.
- منطق کسب‌وکار کاملاً در `services.py` نگه داشته شد و ویوها فقط ورودی/خروجی را مدیریت می‌کنند.
