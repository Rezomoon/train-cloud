# گزارش پیاده‌سازی جریان دو مرحله‌ای خرید VPS و پرداخت آزمایشی

## ۱. خلاصه

طبق فایل `docs/buy-flow.md`، جریان خرید از حالت «ایجاد سفارش + پرداخت خودکار» به **دو مرحله مستقل** تغییر کرد:

1. **مرحله A — ایجاد سفارش:** `POST /api/v1/orders/purchase/`
   سفارش با `status='pending_payment'` و `payment_status='pending'` ساخته می‌شود و **هیچ پرداخت یا ساخت VPS خودکاری انجام نمی‌شود**.
2. **مرحله B — تأیید پرداخت:** `POST /api/v1/orders/<uuid>/pay/`
   کاربر صراحتاً درخواست پرداخت می‌دهد؛ سرویس، کلاینت Mock Payment Gateway را صدا می‌زند، پرداخت را ثبت می‌کند و VPS را می‌سازد و به سفارش متصل می‌کند.

موارد خارج از محدوده (OpenStack، سقف تعداد VPS، حذف/خاتمه VPS و کانتینر جداگانه برای پرداخت) پیاده‌سازی نشدند.

---

## ۲. فایل‌های ایجادشده و تغییرکرده

| فایل | وضعیت | توضیح |
|---|---|---|
| `cloud_project/apps/orders/gateways.py` | ایجاد | کلاینت `MockPaymentGatewayClient` |
| `cloud_project/apps/orders/models.py` | به‌روزرسانی | افزودن `payment_reference` |
| `cloud_project/apps/orders/services.py` | به‌روزرسانی | حذف تریگر خودکار پرداخت + افزودن `process_order_payment` |
| `cloud_project/apps/orders/serializers.py` | به‌روزرسانی | افزودن `payment_reference` به خروجی سفارش |
| `cloud_project/apps/orders/views.py` | به‌روزرسانی | افزودن `PayOrderAPIView` |
| `cloud_project/apps/orders/urls.py` | به‌روزرسانی | افزودن مسیر `<uuid>/pay/` |
| `cloud_project/apps/orders/admin.py` | به‌روزرسانی | نمایش و جستجوی `payment_reference` |
| `cloud_project/apps/orders/tests.py` | بازنویسی | تست‌های جریان دو مرحله‌ای |
| `cloud_project/apps/orders/migrations/0004_order_payment_reference.py` | ایجاد | مایگریشن فیلد `payment_reference` |

---

## ۳. تغییرات مدل `Order`

### ۳-۱. فیلد جدید `payment_reference`

```python
payment_reference = models.CharField(max_length=100, null=True, blank=True)
```

این فیلد شناسه تراکنش برگشتی از درگاه Mock را نگه می‌دارد و در پاسخ API نیز نمایش داده می‌شود.

### ۳-۲. وضعیت‌ها

وضعیت‌های سفارش شامل موارد زیر هستند:

```text
pending_payment, paid, provisioning, active, cancelled, failed
```

### ۳-۳. مایگریشن

```text
apps/orders/migrations/0004_order_payment_reference.py
```

با موفقیت اعمال شد:

```text
Applying orders.0004_order_payment_reference... OK
```

---

## ۴. تغییرات `create_purchase_order`

### ۴-۱. حذف پرداخت خودکار

در نسخه قبلی، بعد از ساخت سفارش این کد اجرا می‌شد:

```python
transaction.on_commit(
    lambda: process_mock_payment_task.delay(str(order.uuid))
)
```

این بخش **کاملاً حذف شد**. اکنون سفارش تا زمانی که کاربر اندپوینت پرداخت را صدا نزند، در وضعیت زیر باقی می‌ماند:

```text
status = pending_payment
payment_status = pending
vps = None
payment_reference = None
```

### ۴-۲. گسترش وضعیت‌های رزروکننده نام

برای جلوگیری از تکرار نام VPS، وضعیت `active` هم به لیست سفارش‌های در جریان اضافه شد:

```python
ACTIVE_ORDER_STATUSES = [
    OrderStatusChoices.PENDING_PAYMENT,
    OrderStatusChoices.PAID,
    OrderStatusChoices.PROVISIONING,
    OrderStatusChoices.ACTIVE,
]
```

بررسی یکتایی نام همچنان داخل `transaction.atomic()` و با قفل ردیف کاربر انجام می‌شود:

```python
User.objects.select_for_update().get(pk=user.pk)
```

### ۴-۳. حفظ اعتبارسنجی‌های قبلی

- بررسی فعال بودن پلن
- بررسی وجود Duration
- تطابق `plan.data_center_id` با `duration.data_center_id`
- بررسی فعال بودن سیستم‌عامل در صورت ارسال
- محاسبه قیمت در سمت سرور: `plan.price * duration.duration_in_month`

---

## ۵. کلاینت Mock Payment Gateway

فایل `apps/orders/gateways.py`:

```python
@dataclass
class PaymentGatewayResponse:
    success: bool
    reference_id: str
    message: str
    raw_payload: dict


class MockPaymentGatewayClient:
    def charge(self, order_uuid, amount, payment_method):
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
```

این کلاس هیچ درخواست شبکه‌ای ارسال نمی‌کند و به‌صورت ماژولار طراحی شده تا بعداً با یک کلاینت HTTP واقعی جایگزین شود.

---

## ۶. سرویس پرداخت `process_order_payment`

تابع جدید در `apps/orders/services.py`:

```python
def process_order_payment(user, order_uuid):
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                uuid=order_uuid,
                user=user,
            )
        except Order.DoesNotExist:
            raise NotFound("Order not found.")
```

### ۶-۱. اعتبارسنجی وضعیت و Idempotency

```python
if (
    order.payment_status == PaymentStatusChoices.COMPLETED
    or order.status in (OrderStatusChoices.PAID, OrderStatusChoices.ACTIVE)
):
    raise ValidationError({"detail": "This order has already been paid."})

if order.status != OrderStatusChoices.PENDING_PAYMENT:
    raise ValidationError(
        {"detail": f"Cannot pay for an order in '{order.status}' status."}
    )
```

- پرداخت دوباره → HTTP 400
- سفارش با وضعیت غیر از `pending_payment` → HTTP 400
- سفارش کاربر دیگر یا UUID ناموجود → HTTP 404

### ۶-۲. فراخوانی درگاه و ثبت موفقیت

```python
gateway_response = MockPaymentGatewayClient().charge(
    order.uuid,
    order.total_amount,
    order.payment_method,
)

if gateway_response.success:
    order.payment_status = PaymentStatusChoices.COMPLETED
    order.status = OrderStatusChoices.PAID
    order.paid_at = timezone.now()
    order.payment_reference = gateway_response.reference_id
    order.save(update_fields=[...])

    create_vps_from_order(order)
    order.refresh_from_db()
```

پس از ثبت پرداخت، تابع `create_vps_from_order` بلافاصله فراخوانی می‌شود تا VPS ساخته و به سفارش متصل شود؛ سپس وضعیت نهایی سفارش از دیتابیس خوانده می‌شود (`active`).

### ۶-۳. مدیریت شکست درگاه

```python
else:
    order.payment_status = PaymentStatusChoices.FAILED
    order.status = OrderStatusChoices.FAILED
    order.save(update_fields=[...])

# خارج از تراکنش:
if not gateway_response.success:
    raise ValidationError({"detail": gateway_response.message})
```

نکته مهم: خطای `ValidationError` **بعد از پایان تراکنش** پرتاب می‌شود تا وضعیت `failed` در دیتابیس ذخیره بماند؛ در غیر این صورت rollback تراکنش آن را پاک می‌کرد.

### ۶-۴. خروجی

```python
return order, gateway_response.raw_payload
```

---

## ۷. اندپوینت پرداخت

### ۷-۱. ویو

```python
class PayOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, uuid):
        order, gateway_payload = process_order_payment(
            user=request.user,
            order_uuid=uuid,
        )
        return Response(
            {
                "order": OrderDetailSerializer(order).data,
                "payment_gateway_response": gateway_payload,
            },
            status=status.HTTP_200_OK,
        )
```

### ۷-۲. مسیر

```python
path("<uuid:uuid>/pay/", PayOrderAPIView.as_view(), name="order-pay"),
```

آدرس نهایی: `POST /api/v1/orders/<uuid>/pay/`

---

## ۸. سریالایزر سفارش

`OrderDetailSerializer` اکنون شامل موارد زیر است:

- `payment_reference`
- `vps` به‌صورت خلاصه (`uuid`, `name`, `ip_address`, `status`) یا `null` قبل از پرداخت

خروجی سفارش قبل از پرداخت:

```json
{
  "status": "pending_payment",
  "payment_status": "pending",
  "payment_reference": null,
  "vps": null
}
```

خروجی بعد از پرداخت:

```json
{
  "status": "active",
  "payment_status": "completed",
  "payment_reference": "MOCK-PAY-XXXXXXXXXXXX",
  "vps": {
    "uuid": "...",
    "name": "My VPS",
    "ip_address": "10.10.0.15",
    "status": "active"
  }
}
```

---

## ۹. اندپوینت لیست VPS

اندپوینت `GET /api/v1/vps/` از قبل وجود داشت و بدون تغییر باقی ماند:

```python
class VPSListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        vps_list = VPS.objects.filter(user=request.user)
        serializer = VPSSerializer(vps_list, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
```

---

## ۱۰. تست‌ها

فایل `apps/orders/tests.py` بازنویسی شد و ۱۹ تست برای جریان جدید نوشته شد.

پوشش تست‌ها:

1. ساخت سفارش با Snapshot صحیح و بدون پرداخت/VPS.
2. خطای 400 برای عدم تطابق DataCenter.
3. خطای 400 برای پلن غیرفعال.
4. پاسخ 201 اندپوینت خرید با `vps=null` و بدون رکورد VPS.
5. محدود بودن جزئیات سفارش به کاربر مالک.
6. نام تکراری در VPS موجود → 400.
7. نام تکراری در سفارش فعال → 400 (case-insensitive).
8. امکان نام یکسان برای دو کاربر مختلف.
9. یکتایی case-insensitive در سطح دیتابیس.
10. اتصال VPS به سفارش و Idempotency تابع ساخت VPS.
11. علامت‌گذاری سفارش به `failed` در صورت نام تکراری هنگام Provisioning.
12. پرداخت موفق، ثبت `paid_at` و `payment_reference` و ساخت VPS.
13. پاسخ اندپوینت پرداخت شامل سفارش و پاسخ درگاه.
14. پرداخت دوباره → 400 و بدون VPS تکراری.
15. پرداخت سفارش کاربر دیگر → 404.
16. پرداخت سفارش با وضعیت غیرمجاز → 400.
17. شکست درگاه → وضعیت `failed` و بدون VPS.
18. لیست VPS فقط برای کاربر جاری.
19. سایر تست‌های یکتایی و اعتبارسنجی.

نتیجه اجرا:

```text
Found 19 test(s).
System check identified no issues (0 silenced).
...................
Ran 19 tests in 9.443s

OK
```

بررسی‌های تکمیلی:

```text
manage.py check            -> no issues
makemigrations --check     -> No changes detected
```

---

## ۱۱. تست End-to-End واقعی (Docker)

جریان کامل روی کانتینرهای واقعی تست شد:

1. `POST /api/v1/orders/purchase/` → `201 Created`
   - `status="pending_payment"`
   - `payment_status="pending"`
   - `vps=null`
   - `payment_reference=null`
2. `GET /api/v1/vps/` قبل از پرداخت → `[]`
3. `POST /api/v1/orders/<uuid>/pay/` → `200 OK`
   - `status="active"`
   - `payment_status="completed"`
   - `payment_reference="MOCK-PAY-..."`
   - `vps` ساخته و متصل شد
4. پرداخت دوم → `400 Bad Request`
   ```json
   {"detail": "This order has already been paid."}
   ```
5. `GET /api/v1/vps/` بعد از پرداخت → شامل VPS ساخته‌شده
6. خرید دوباره با همان نام (case-insensitive) → `400 Bad Request`
   ```json
   {"vps_name": "You already have a VPS or active order with this name."}
   ```

---

## ۱۲. تطابق با معیارهای پذیرش

| معیار | وضعیت |
|---|---|
| خرید، سفارش `pending_payment` با `vps=None` می‌سازد و VPS نمی‌سازد | ✅ تست شده |
| خرید دوباره با نام یکسان → HTTP 400 | ✅ تست شده |
| پرداخت، وضعیت را `completed`/`active` می‌کند و VPS می‌سازد | ✅ تست شده |
| پرداخت دوباره → HTTP 400 بدون VPS تکراری | ✅ تست شده |
| `GET /api/v1/vps/` VPS جدید را برمی‌گرداند | ✅ تست شده |
| ثبت `paid_at` و `payment_reference` | ✅ تست شده |
| عدم فراخوانی درگاه واقعی | ✅ Mock Gateway |

---

## ۱۳. نحوه اجرا

```bash
docker compose up --build
```

- API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- Redis: داخلی کانتینرها

اجرای تست‌ها:

```bash
cd cloud_project
../.venv/bin/python manage.py test apps.orders
```

---

## ۱۴. نمونه فراخوانی API

### ۱۴-۱. مرحله A — ایجاد سفارش

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

### ۱۴-۲. مرحله B — پرداخت

```bash
curl -X POST http://localhost:8000/api/v1/orders/<ORDER_UUID>/pay/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

پاسخ:

```json
{
  "order": {
    "uuid": "...",
    "status": "active",
    "payment_status": "completed",
    "payment_reference": "MOCK-PAY-XXXXXXXXXXXX",
    "vps": {
      "uuid": "...",
      "name": "My VPS",
      "ip_address": "10.10.0.15",
      "status": "active"
    }
  },
  "payment_gateway_response": {
    "order_uuid": "...",
    "amount": "300000.00",
    "payment_method": "bank",
    "gateway": "mock_container_v1",
    "status": "APPROVED",
    "reference_id": "MOCK-PAY-XXXXXXXXXXXX"
  }
}
```

### ۱۴-۳. لیست VPS

```bash
curl http://localhost:8000/api/v1/vps/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## ۱۵. تصمیم‌های فنی

- پرداخت از ایجاد سفارش جدا شد و فقط با فراخوانی صریح اندپوینت `/pay/` انجام می‌شود.
- درگاه پرداخت به‌صورت کلاس مستقل در `gateways.py` پیاده شد تا جایگزینی آن با سرویس واقعی ساده باشد.
- `process_order_payment` از `select_for_update` استفاده می‌کند تا پرداخت همزمان یک سفارش دوبار انجام نشود.
- خطای درگاه بعد از Commit تراکنش پرتاب می‌شود تا وضعیت `failed` از بین نرود.
- ساخت VPS به‌صورت همزمان (synchronous) بعد از پرداخت انجام می‌شود تا پاسخ API وضعیت نهایی `active` را نشان دهد.
- تسک‌های Celery قبلی (`process_mock_payment_task` و `provision_vps_task`) در کد باقی مانده‌اند اما دیگر از مسیر خرید فراخوانی نمی‌شوند؛ جریان جدید کاملاً از سرویس `process_order_payment` استفاده می‌کند.
- `payment_reference` در پنل ادمین قابل مشاهده و جستجو است.
