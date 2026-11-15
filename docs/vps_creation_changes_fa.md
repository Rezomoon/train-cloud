# گزارش پیاده‌سازی ساخت VPS پس از پرداخت و یکتایی نام VPS

## ۱. خلاصه

طبق فایل `docs/vps_creation_and_name_constraint.md`، دو هدف اصلی پیاده‌سازی شد:

1. **یکتایی نام VPS برای هر کاربر** در سه لایه:
   - دیتابیس (Constraint)
   - لایه سرویس (اعتبارسنجی قبل از ساخت سفارش)
   - کنترل همزمانی با قفل ردیف کاربر
2. **ساخت رکورد VPS بعد از پرداخت موفق** و اتصال آن به سفارش، به‌صورت غیرهمزمان و Idempotent.

موارد خارج از محدوده (OpenStack، سقف تعداد VPS و حذف/خاتمه VPS) پیاده‌سازی نشدند.

نتیجه نهایی:

- Constraint یکتایی case-insensitive روی `(Lower('name'), user)` اضافه شد.
- فیلد `operating_system` به مدل `VPS` اضافه شد.
- وضعیت‌های `provisioning` و `active` به وضعیت‌های سفارش اضافه شدند.
- سرویس `create_vps_from_order` ساخته شد.
- تسک `provision_vps_task` اضافه و از تسک پرداخت فراخوانی شد.
- خروجی سفارش شامل اطلاعات VPS شد.
- اندپوینت `GET /api/v1/vps/` اضافه شد.
- مایگریشن‌ها ساخته و اعمال شدند.
- ۱۵ تست خودکار با موفقیت اجرا شد.

---

## ۲. فایل‌های ایجادشده و تغییرکرده

| فایل | وضعیت | توضیح |
|---|---|---|
| `cloud_project/apps/vps/models.py` | به‌روزرسانی | افزودن `operating_system` و `UniqueConstraint` |
| `cloud_project/apps/vps/services.py` | ایجاد | تابع `create_vps_from_order` |
| `cloud_project/apps/vps/api/views.py` | به‌روزرسانی | افزودن `VPSListView` |
| `cloud_project/apps/vps/urls.py` | به‌روزرسانی | مسیر `GET /api/v1/vps/` |
| `cloud_project/apps/orders/models.py` | به‌روزرسانی | افزودن وضعیت‌های `provisioning` و `active` |
| `cloud_project/apps/orders/services.py` | به‌روزرسانی | بررسی یکتایی نام و قفل کاربر |
| `cloud_project/apps/orders/tasks.py` | به‌روزرسانی | افزودن `provision_vps_task` و فراخوانی بعد از Commit |
| `cloud_project/apps/orders/serializers.py` | به‌روزرسانی | افزودن خلاصه VPS به خروجی سفارش |
| `cloud_project/apps/orders/tests.py` | به‌روزرسانی | افزودن تست‌های یکتایی نام، ساخت VPS و جریان کامل |
| `cloud_project/apps/orders/migrations/0003_alter_order_status.py` | ایجاد | مایگریشن وضعیت‌های سفارش |
| `cloud_project/apps/vps/migrations/0004_historicalvps_operating_system_vps_operating_system_and_more.py` | ایجاد | مایگریشن فیلد OS و Constraint |

---

## ۳. تغییرات مدل `VPS`

### ۳-۱. فیلد `ip_address`

فیلد `ip_address` از قبل به‌صورت Nullable تعریف شده بود و تغییری لازم نداشت:

```python
ip_address = models.GenericIPAddressField(null=True, blank=True)
```

### ۳-۲. فیلد `operating_system`

برای نگه‌داشتن ارجاع سیستم‌عامل در VPS:

```python
operating_system = models.ForeignKey(
    'infrastructure.OperatingSystem',
    on_delete=models.PROTECT,
    null=True,
    blank=True,
)
```

### ۳-۳. Constraint یکتایی نام به‌ازای هر کاربر

```python
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower

class VPS(AuditModel):
    ...

    class Meta:
        constraints = [
            UniqueConstraint(
                Lower('name'),
                'user',
                name='unique_vps_name_per_user',
            )
        ]
```

این Constraint:

- نام را **case-insensitive** بررسی می‌کند (`Ali` و `ali` یکسان هستند).
- دامنه یکتایی را **به‌ازای هر کاربر** اعمال می‌کند؛ بنابراین دو کاربر مختلف می‌توانند نام یکسان داشته باشند.

---

## ۴. تغییر وضعیت‌های سفارش

در `apps/orders/models.py`، وضعیت‌های `provisioning` و `active` اضافه شدند:

```python
class OrderStatusChoices(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Pending Payment"
    PAID = "paid", "Paid"
    PROVISIONING = "provisioning", "Provisioning"
    ACTIVE = "active", "Active"
    CANCELLED = "cancelled", "Cancelled"
    FAILED = "failed", "Failed"
```

چرخه عمر نهایی:

```text
pending_payment -> paid -> active
                         \-> failed (در صورت خطای یکتایی نام)
```

---

## ۵. اعتبارسنجی یکتایی نام در لایه سرویس

تابع `create_purchase_order` به‌روزرسانی شد تا قبل از ساخت سفارش، نام VPS را بررسی کند.

### ۵-۱. بررسی در VPSهای موجود و سفارش‌های فعال

```python
resolved_vps_name = vps_name or "My VPS"

with transaction.atomic():
    User.objects.select_for_update().get(pk=user.pk)

    name_taken = (
        VPS.objects.filter(
            user=user,
            name__iexact=resolved_vps_name,
        ).exists()
        or Order.objects.filter(
            user=user,
            vps_name__iexact=resolved_vps_name,
            status__in=ACTIVE_ORDER_STATUSES,
        ).exists()
    )
    if name_taken:
        raise ValidationError(
            {
                "vps_name": (
                    "You already have a VPS or active order with this name."
                )
            }
        )
```

وضعیت‌های فعال سفارش که نام را رزرو می‌کنند:

```python
ACTIVE_ORDER_STATUSES = [
    OrderStatusChoices.PENDING_PAYMENT,
    OrderStatusChoices.PAID,
    OrderStatusChoices.PROVISIONING,
]
```

### ۵-۲. کنترل همزمانی

- کل بررسی و ساخت سفارش داخل `transaction.atomic()` انجام می‌شود.
- با `User.objects.select_for_update().get(pk=user.pk)` ردیف کاربر قفل می‌شود تا دو درخواست همزمان از یک کاربر نتوانند هر دو از بررسی عبور کنند.
- بررسی سفارش‌های در جریان (`pending_payment`، `paid`، `provisioning`) از Race Condition قبل از ساخت اولین VPS جلوگیری می‌کند.

در صورت تکراری بودن نام، خطای `ValidationError` پرتاب می‌شود که خروجی آن HTTP 400 با کلید `vps_name` است.

---

## ۶. سرویس ساخت VPS (`apps/vps/services.py`)

تابع `create_vps_from_order`:

```python
def create_vps_from_order(order: Order) -> Optional[VPS]:
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)

        if order.vps_id:
            return order.vps

        try:
            with transaction.atomic():
                vps = VPS.objects.create(
                    user=order.user,
                    plan=order.plan,
                    duration=order.duration,
                    operating_system=order.operating_system,
                    name=order.vps_name,
                    # TODO: Replace mock IP/status with Infrastructure Provider
                    ip_address="10.10.0.15",
                    status=StatusChoices.Active,
                )
        except IntegrityError:
            order.status = OrderStatusChoices.FAILED
            order.save(update_fields=["status", "updated_at"])
            return None

        order.vps = vps
        order.status = OrderStatusChoices.ACTIVE
        order.save(update_fields=["vps", "status", "updated_at"])

        return vps
```

نکات مهم:

- **Idempotent:** اگر `order.vps` قبلاً مقدار داشته باشد، همان VPS برگردانده می‌شود و رکورد جدیدی ساخته نمی‌شود.
- **قفل ردیف سفارش:** با `select_for_update()` از پردازش همزمان جلوگیری می‌شود.
- **مدیریت `IntegrityError`:** اگر به هر دلیل (مثلاً Race Condition) نام تکراری باشد، VPS ساخته نمی‌شود و وضعیت سفارش `failed` می‌شود.
- **Savepoint داخلی:** خطای یکتایی باعث خراب شدن تراکنش بیرونی نمی‌شود و امکان ذخیره وضعیت `failed` وجود دارد.
- **IP آزمایشی:** مقدار `10.10.0.15` و وضعیت `active` برای شبیه‌سازی Provisioning استفاده شده و با TODO مشخص شده است.

---

## ۷. تسک‌های Celery

### ۷-۱. تسک Provisioning

```python
@shared_task
def provision_vps_task(order_uuid: str):
    order = Order.objects.get(uuid=order_uuid)
    return create_vps_from_order(order)
```

### ۷-۲. اتصال به تسک پرداخت

بعد از ثبت پرداخت موفق، تسک Provisioning فقط پس از Commit شدن تراکنش ارسال می‌شود:

```python
order.payment_status = PaymentStatusChoices.COMPLETED
order.status = OrderStatusChoices.PAID
order.paid_at = timezone.now()
order.save(update_fields=[...])

transaction.on_commit(
    lambda: provision_vps_task.delay(str(order.uuid))
)
```

این جداسازی باعث می‌شود:

- پرداخت و ساخت VPS از هم مستقل باشند.
- در صورت شکست Provisioning، وضعیت پرداخت از بین نرود.
- اجرای دوباره تسک‌ها به‌خاطر Idempotency مشکلی ایجاد نکند.

---

## ۸. نمایش VPS در خروجی سفارش

در `apps/orders/serializers.py` یک سریالایزر خلاصه اضافه شد:

```python
class OrderVPSSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = VPS
        fields = ["uuid", "name", "ip_address", "status"]
```

و در `OrderDetailSerializer`:

```python
vps = OrderVPSSummarySerializer(read_only=True)
```

بنابراین خروجی `GET /api/v1/orders/<uuid>/` پس از Provisioning شامل این بخش است:

```json
{
  "uuid": "...",
  "vps_name": "My VPS",
  "status": "active",
  "payment_status": "completed",
  "vps": {
    "uuid": "...",
    "name": "My VPS",
    "ip_address": "10.10.0.15",
    "status": "active"
  }
}
```

قبل از Provisioning، مقدار `vps` برابر `null` است.

---

## ۹. اندپوینت لیست VPS

### ۹-۱. ویو

```python
class VPSListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vps_list = VPS.objects.filter(user=request.user)
        serializer = VPSSerializer(vps_list, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
```

### ۹-۲. مسیر

```python
path("", VPSListView.as_view(), name="vps-list"),
```

آدرس نهایی: `GET /api/v1/vps/`

- فقط VPSهای کاربر احراز هویت‌شده برگردانده می‌شوند.
- در صورت نبود VPS، لیست خالی `[]` برمی‌گردد.

> نکته: ویو و مسیر قدیمی `purchase/` در اپ `vps` خارج از محدوده این تسک بود و تغییری نکرد.

---

## ۱۰. مایگریشن‌ها

### ۱۰-۱. `orders/0003_alter_order_status.py`

- به‌روزرسانی `choices` فیلد `status` برای افزودن `provisioning` و `active`.

### ۱۰-۲. `vps/0004_historicalvps_operating_system_vps_operating_system_and_more.py`

- افزودن `operating_system` به مدل `VPS`.
- افزودن `operating_system` به مدل تاریخی `HistoricalVPS`.
- ایجاد Constraint `unique_vps_name_per_user`.

هر دو مایگریشن با موفقیت اعمال شدند:

```text
Applying orders.0003_alter_order_status... OK
Applying vps.0004_historicalvps_operating_system_vps_operating_system_and_more... OK
```

---

## ۱۱. تست‌ها

تعداد تست‌ها از ۷ به ۱۵ افزایش یافت. تست‌های جدید:

1. نام تکراری در VPSهای موجود → خطای 400.
2. نام تکراری در سفارش‌های فعال → خطای 400 (case-insensitive).
3. امکان استفاده از نام یکسان توسط دو کاربر مختلف.
4. یکتایی case-insensitive در سطح دیتابیس (`IntegrityError`).
5. ساخت VPS از سفارش، اتصال به سفارش و Idempotency.
6. علامت‌گذاری سفارش به `failed` در صورت تکراری بودن نام هنگام Provisioning.
7. جریان کامل پرداخت → Provisioning → وضعیت `active` و اتصال VPS.
8. اندپوینت `GET /api/v1/vps/` و محدود بودن آن به VPSهای کاربر جاری.

نتیجه اجرا:

```text
Found 15 test(s).
System check identified no issues (0 silenced).
...............
Ran 15 tests in 6.632s

OK
```

بررسی‌های تکمیلی:

```text
manage.py check            -> no issues
makemigrations --check     -> No changes detected
```

---

## ۱۲. تطابق با معیارهای پذیرش

| معیار | وضعیت |
|---|---|
| نام تکراری در VPS یا سفارش فعال → HTTP 400 | ✅ تست شده |
| دو کاربر مختلف بتوانند نام یکسان داشته باشند | ✅ تست شده |
| پس از خرید: `payment_status=completed`، `status=active` و `order.vps` مقداردار | ✅ تست شده |
| ساخت VPS با نام، پلن و مدت‌زمان صحیح برای همان کاربر | ✅ تست شده |
| `GET /api/v1/vps/` لیست VPSهای کاربر را برمی‌گرداند | ✅ تست شده |
| یکتایی نام در سطح دیتابیس | ✅ Constraint اضافه شد |
| Idempotency ساخت VPS | ✅ تست شده |
| مدیریت خطای تکراری بودن نام در Provisioning | ✅ تست شده |

---

## ۱۳. نحوه اجرا

از پوشه `cloud_project`:

```bash
# اجرای PostgreSQL و Redis
docker compose up -d

# اعمال مایگریشن‌ها
../.venv/bin/python manage.py migrate

# اجرای سرور
../.venv/bin/python manage.py runserver

# اجرای Worker در ترمینال جداگانه
../.venv/bin/celery -A cloud_project worker -l info
```

اجرای تست‌ها:

```bash
../.venv/bin/python manage.py test apps.orders
```

---

## ۱۴. نمونه جریان کامل

### ۱۴-۱. خرید VPS

```bash
curl -X POST http://localhost:8000/api/v1/orders/purchase/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_uuid": "<PLAN_UUID>",
    "duration_uuid": "<DURATION_UUID>",
    "operating_system_uuid": "<OS_UUID>",
    "vps_name": "My VPS"
  }'
```

پاسخ اولیه: `201 Created` با `status="pending_payment"` و `vps=null`.

### ۱۴-۲. بررسی وضعیت سفارش

```bash
curl http://localhost:8000/api/v1/orders/<ORDER_UUID>/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

پس از اجرای Worker:

```json
{
  "status": "active",
  "payment_status": "completed",
  "paid_at": "...",
  "vps": {
    "uuid": "...",
    "name": "My VPS",
    "ip_address": "10.10.0.15",
    "status": "active"
  }
}
```

### ۱۴-۳. لیست VPSهای کاربر

```bash
curl http://localhost:8000/api/v1/vps/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## ۱۵. تصمیم‌های فنی

- Constraint با `Lower('name')` پیاده شد تا یکتایی بدون حساسیت به حروف بزرگ/کوچک باشد.
- قفل کاربر (`select_for_update`) در سرویس خرید قرار گرفت تا بررسی نام و ساخت سفارش در یک واحد اتمیک انجام شود.
- Provisioning از پرداخت جدا شد و با `transaction.on_commit` بعد از Commit پرداخت ارسال می‌شود.
- `create_vps_from_order` کاملاً Idempotent است تا اجرای دوباره تسک رکورد تکراری نسازد.
- در صورت خطای یکتایی نام در زمان Provisioning، سفارش به `failed` تغییر می‌کند و API از کار نمی‌افتد.
- IP و وضعیت VPS فعلاً مقادیر Mock هستند و محل جایگزینی آن‌ها با Provider واقعی با TODO مشخص شده است.
