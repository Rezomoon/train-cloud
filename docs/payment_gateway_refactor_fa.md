# گزارش بازطراحی درگاه پرداخت آزمایشی و اندپوینت پرداخت سفارش

## ۱. خلاصه

در این تغییرات، درگاه پرداخت Mock از حالت کلاس‌محور به یک تابع ساده تبدیل شد و اندپوینت پرداخت سفارش بازطراحی شد تا:

- امکان شبیه‌سازی شکست پرداخت از طریق ورودی API فراهم شود.
- در صورت شکست، پاسخ HTTP 400 همراه با داده‌های به‌روزشده سفارش و پاسخ درگاه برگردد.
- در صورت موفقیت، پاسخ HTTP 200 شامل اطلاعات کامل VPS ساخته‌شده باشد.
- هیچ ارجاعی به کلاس‌های قبلی `MockPaymentGatewayClient` و `PaymentGatewayResponse` در کد و تست‌ها باقی نماند.

---

## ۲. چرا این تغییر انجام شد؟

نسخه قبلی از یک کلاس و dataclass برای درگاه Mock استفاده می‌کرد. این ساختار برای یک شبیه‌ساز ساده، پیچیده‌تر از حد لازم بود و تست شکست پرداخت را دشوار می‌کرد. همچنین در صورت شکست درگاه، سرویس خطا پرتاب می‌کرد و امکان برگرداندن داده‌های به‌روزشده سفارش در بدنه پاسخ وجود نداشت.

اهداف بازطراحی:

1. **سادگی:** جایگزینی کلاس و dataclass با یک تابع خالص (pure function) که فقط یک دیکشنری برمی‌گرداند.
2. **قابلیت تست شکست:** پارامتر `simulate_failure` اجازه می‌دهد سناریوی پرداخت ناموفق بدون patch کردن کلاس تست شود.
3. **پاسخ شفاف‌تر:** در شکست، API هم داده سفارش و هم پاسخ درگاه را با وضعیت 400 برمی‌گرداند.
4. **نمایش کامل VPS:** پاسخ موفق شامل جزئیات کامل VPS هم داخل `order.vps` و هم در کلید سطح‌بالای `vps` است.

---

## ۳. تغییرات `apps/orders/gateways.py`

### ۳-۱. حذف کلاس‌ها و dataclass

موارد زیر حذف شدند:

- `PaymentGatewayResponse`
- `MockPaymentGatewayClient`

### ۳-۲. تابع جدید `charge_mock_payment`

```python
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
```

### ۳-۳. رفتار تابع

- `simulate_failure=False` (پیش‌فرض): پرداخت موفق با `status="APPROVED"` و شناسه `MOCK-PAY-...`.
- `simulate_failure=True`: پرداخت ناموفق با `status="FAILED"` و شناسه `MOCK-FAIL-...`.
- هیچ درخواست شبکه‌ای ارسال نمی‌شود.

---

## ۴. تغییرات `apps/orders/services.py`

### ۴-۱. امضای جدید `process_order_payment`

```python
def process_order_payment(user, order_uuid, simulate_failure=False):
```

پارامتر `simulate_failure` مستقیماً به `charge_mock_payment` پاس داده می‌شود.

### ۴-۲. فراخوانی درگاه

```python
gateway_response = charge_mock_payment(
    order.uuid,
    order.total_amount,
    order.payment_method,
    simulate_failure=simulate_failure,
)
```

### ۴-۳. مسیر موفقیت

```python
if gateway_response["success"]:
    order.payment_status = PaymentStatusChoices.COMPLETED
    order.status = OrderStatusChoices.PAID
    order.paid_at = timezone.now()
    order.payment_reference = gateway_response["reference_id"]
    order.save(update_fields=[...])

    create_vps_from_order(order)
    order.refresh_from_db()
```

نتیجه:

- `payment_status = "completed"`
- `status = "active"` (بعد از ساخت VPS)
- `paid_at` مقدار می‌گیرد
- `payment_reference` با شناسه درگاه پر می‌شود
- VPS ساخته و به سفارش متصل می‌شود

### ۴-۴. مسیر شکست

```python
else:
    order.payment_status = PaymentStatusChoices.FAILED
    order.status = OrderStatusChoices.FAILED
    order.payment_reference = gateway_response["reference_id"]
    order.save(
        update_fields=[
            "payment_status",
            "status",
            "payment_reference",
            "updated_at",
        ]
    )
```

در این حالت:

- `payment_status = "failed"`
- `status = "failed"`
- `payment_reference` با شناسه `MOCK-FAIL-...` ذخیره می‌شود
- **هیچ VPS ساخته نمی‌شود**
- سرویس خطا پرتاب نمی‌کند و `(order, gateway_response)` را برمی‌گرداند تا ویو بتواند پاسخ 400 با داده‌ها بسازد.

### ۴-۵. خروجی سرویس

```python
return order, gateway_response
```

---

## ۵. تغییرات `apps/orders/serializers.py`

### ۵-۱. سریالایزر کامل VPS

`OrderVPSSummarySerializer` به `OrderVPSDetailSerializer` تغییر کرد و فیلدهای کامل‌تری دارد:

```python
class OrderVPSDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = VPS
        fields = [
            "uuid",
            "name",
            "ip_address",
            "status",
            "plan",
            "duration",
            "operating_system",
            "created_at",
        ]
```

### ۵-۲. سریالایزر ورودی پرداخت

```python
class PayOrderInputSerializer(serializers.Serializer):
    simulate_failure = serializers.BooleanField(required=False, default=False)
```

`BooleanField` در DRF مقادیر `true`/`false` و رشته‌های `"true"`/`"false"` را به‌درستی تفسیر می‌کند.

### ۵-۳. خروجی سفارش

`OrderDetailSerializer` از `OrderVPSDetailSerializer` برای فیلد `vps` استفاده می‌کند؛ بنابراین VPS برگشتی شامل تمام جزئیات خواسته‌شده است.

---

## ۶. تغییرات `apps/orders/views.py`

### ۶-۱. دریافت `simulate_failure`

```python
input_serializer = PayOrderInputSerializer(data=request.data)
input_serializer.is_valid(raise_exception=True)

order, gateway_payload = process_order_payment(
    user=request.user,
    order_uuid=uuid,
    simulate_failure=input_serializer.validated_data["simulate_failure"],
)
```

### ۶-۲. ساخت پاسخ

```python
vps_data = (
    OrderVPSDetailSerializer(order.vps).data
    if order.vps_id
    else None
)

response_status = (
    status.HTTP_200_OK
    if gateway_payload["success"]
    else status.HTTP_400_BAD_REQUEST
)

return Response(
    {
        "order": OrderDetailSerializer(order).data,
        "payment_gateway_response": gateway_payload,
        "vps": vps_data,
    },
    status=response_status,
)
```

### ۶-۳. ساختار پاسخ

پاسخ موفق (`200 OK`):

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
      "status": "active",
      "plan": "...",
      "duration": "...",
      "operating_system": "...",
      "created_at": "..."
    }
  },
  "payment_gateway_response": {
    "success": true,
    "reference_id": "MOCK-PAY-XXXXXXXXXXXX",
    "message": "Mock payment processed successfully.",
    "order_uuid": "...",
    "amount": "60000.00",
    "payment_method": "bank",
    "gateway": "mock_container_v1",
    "status": "APPROVED"
  },
  "vps": {
    "uuid": "...",
    "name": "My VPS",
    "ip_address": "10.10.0.15",
    "status": "active",
    "plan": "...",
    "duration": "...",
    "operating_system": "...",
    "created_at": "..."
  }
}
```

پاسخ ناموفق (`400 Bad Request`):

```json
{
  "order": {
    "uuid": "...",
    "status": "failed",
    "payment_status": "failed",
    "payment_reference": "MOCK-FAIL-XXXXXXXXXXXX",
    "vps": null
  },
  "payment_gateway_response": {
    "success": false,
    "reference_id": "MOCK-FAIL-XXXXXXXXXXXX",
    "message": "Mock payment declined by gateway.",
    "order_uuid": "...",
    "amount": "60000.00",
    "payment_method": "bank",
    "gateway": "mock_container_v1",
    "status": "FAILED"
  },
  "vps": null
}
```

---

## ۷. پاک‌سازی کد

- کلاس `MockPaymentGatewayClient` حذف شد.
- dataclass `PaymentGatewayResponse` حذف شد.
- تمام ارجاع‌ها در `services.py`، `views.py` و `tests.py` به تابع `charge_mock_payment` و دیکشنری‌ها تغییر کردند.
- بررسی نهایی:

```text
grep -rn "MockPaymentGatewayClient\|PaymentGatewayResponse" cloud_project --include='*.py'
-> no code references
```

---

## ۸. تست‌ها

تست‌ها به‌روزرسانی شدند و تعداد آن‌ها به ۲۰ رسید. موارد جدید/تغییریافته:

1. تست موفقیت پرداخت با دیکشنری پاسخ درگاه.
2. تست شکست پرداخت با `simulate_failure=True` در سطح سرویس.
3. تست اندپوینت پرداخت با `{"simulate_failure": true}` و بررسی پاسخ 400.
4. بررسی وجود کلید سطح‌بالای `vps` و فیلدهای کامل آن در پاسخ موفق.
5. بررسی عدم ساخت VPS در پرداخت ناموفق.
6. بررسی ذخیره `payment_reference` با پیشوند `MOCK-FAIL-` در شکست.

نتیجه اجرا:

```text
Found 20 test(s).
System check identified no issues (0 silenced).
....................
Ran 20 tests in 9.665s

OK
```

بررسی‌های تکمیلی:

```text
manage.py check            -> no issues
makemigrations --check     -> No changes detected
```

---

## ۹. تست End-to-End واقعی

جریان روی کانتینرهای Docker تست شد.

### ۹-۱. پرداخت موفق

```bash
curl -X POST http://localhost:8000/api/v1/orders/<ORDER_UUID>/pay/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

نتیجه:

- HTTP `200 OK`
- `order.status = "active"`
- `order.payment_status = "completed"`
- `order.payment_reference = "MOCK-PAY-..."`
- `order.vps` کامل و مقداردار
- کلید سطح‌بالای `vps` کامل و مقداردار
- `payment_gateway_response.status = "APPROVED"`

### ۹-۲. پرداخت ناموفق

```bash
curl -X POST http://localhost:8000/api/v1/orders/<ORDER_UUID>/pay/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"simulate_failure": true}'
```

نتیجه:

- HTTP `400 Bad Request`
- `order.status = "failed"`
- `order.payment_status = "failed"`
- `order.payment_reference = "MOCK-FAIL-..."`
- `order.vps = null`
- کلید سطح‌بالای `vps = null`
- `payment_gateway_response.status = "FAILED"`
- هیچ رکورد VPS ساخته نشد

---

## ۱۰. نحوه استفاده

### پرداخت موفق (پیش‌فرض)

```bash
curl -X POST http://localhost:8000/api/v1/orders/<ORDER_UUID>/pay/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### شبیه‌سازی شکست

```bash
curl -X POST http://localhost:8000/api/v1/orders/<ORDER_UUID>/pay/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"simulate_failure": true}'
```

---

## ۱۱. تصمیم‌های فنی

- تابع `charge_mock_payment` بدون وابستگی به Django یا DRF است و فقط `uuid` و `Decimal` را import می‌کند؛ بنابراین به‌سادگی قابل تست و جایگزینی است.
- سرویس در شکست درگاه خطا پرتاب نمی‌کند؛ این کار به ویو اجازه می‌دهد بدنه پاسخ شامل سفارش و پاسخ درگاه باشد و وضعیت HTTP را دقیق تعیین کند.
- `payment_reference` در هر دو حالت موفق و ناموفق ذخیره می‌شود تا سابقه تراکنش کامل باشد.
- در پرداخت ناموفق، عمداً هیچ VPS ساخته نمی‌شود.
- اطلاعات VPS در دو محل (`order.vps` و کلید `vps`) برگردانده می‌شود تا کلاینت‌ها به هر دو شکل سازگار باشند.
- خطاهای مربوط به سفارش (پرداخت دوباره، وضعیت غیرمجاز و سفارش کاربر دیگر) همچنان از طریق `ValidationError` و `NotFound` مدیریت می‌شوند.
