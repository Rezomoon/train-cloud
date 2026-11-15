# گزارش پیاده‌سازی اسنپ‌شات منابع سخت‌افزاری روی مدل VPS

## ۱. خلاصه

پیش از این، مشخصات سخت‌افزاری هر VPS فقط از طریق `Plan` مربوطه خوانده می‌شد. بنابراین اگر ادمین بعداً `cpu`، `ram` یا `storage` یک پلن را تغییر می‌داد، مشخصات نمایش‌داده‌شده برای VPSهای فروخته‌شده نیز تغییر می‌کرد؛ در حالی که کاربر قبلاً منابع دیگری خریداری کرده بود.

در این تغییرات، سه فیلد `cpu`، `ram` و `storage` مستقیماً روی مدل `VPS` اضافه شدند تا هر VPS مشخصات خریداری‌شده خود را برای همیشه نگه دارد، مستقل از تغییرات آینده `Plan`.

---

## ۲. چرا این تغییر لازم بود؟

- **صحت داده:** کاربر باید دقیقاً همان منابعی را داشته باشد که برای آن پول پرداخت کرده است.
- **استقلال از پلن:** ویرایش یا حذف یک پلن نباید مشخصات VPSهای موجود را تغییر دهد.
- **شفافیت API:** پاسخ‌های API باید مقدار واقعی ذخیره‌شده روی VPS را برگردانند، نه مقدار لحظه‌ای پلن.
- **سابقه تاریخی:** مدل `VPS` از `HistoricalRecords` استفاده می‌کند؛ این فیلدها در تاریخچه نیز حفظ می‌شوند.

---

## ۳. تغییرات مدل (`apps/vps/models.py`)

سه فیلد غیر nullable به مدل `VPS` اضافه شد:

```python
class VPS(AuditModel):
    ...
    # Hardware snapshot captured at purchase time so later Plan changes do not
    # affect already provisioned VPS instances.
    cpu = models.IntegerField()
    ram = models.IntegerField()
    storage = models.IntegerField()

    history = HistoricalRecords()
```

نکته: چون `VPS` از `HistoricalRecords` استفاده می‌کند، همین فیلدها به‌صورت خودکار در مدل `HistoricalVPS` نیز وجود دارند.

---

## ۴. مایگریشن (`apps/vps/migrations/0005_vps_hardware_snapshots.py`)

### ۴-۱. چالش رکوردهای موجود

در دیتابیس از قبل چند رکورد `VPS` وجود داشت. اضافه کردن فیلد غیر nullable بدون مقدار پیش‌فرض، مایگریشن را با خطا مواجه می‌کرد.

### ۴-۲. راه‌حل

مایگریشن در دو مرحله انجام می‌شود:

1. **افزودن فیلدها با `default=0` و `preserve_default=False`:**

```python
migrations.AddField(
    model_name="vps",
    name="cpu",
    field=models.IntegerField(default=0),
    preserve_default=False,
)
```

`preserve_default=False` باعث می‌شود بعد از مایگریشن، فیلد در مدل نهایی بدون default باقی بماند و همچنان اجباری باشد. این روش از حالت nullable موقت جلوگیری می‌کند و نیازی به `AlterField` دوم ندارد.

همین کار برای `ram`، `storage` و مدل `historicalvps` نیز انجام شد.

2. **پر کردن داده‌ها با `RunPython`:**

```python
def populate_hardware_snapshots(apps, schema_editor):
    VPS = apps.get_model("vps", "VPS")
    HistoricalVPS = apps.get_model("vps", "HistoricalVPS")
    Plan = apps.get_model("vps", "Plan")

    plans = {plan.pk: plan for plan in Plan.objects.all()}

    for vps in VPS.objects.all().iterator():
        plan = plans.get(vps.plan_id)
        if plan is None:
            continue
        vps.cpu = plan.cpu
        vps.ram = plan.ram
        vps.storage = plan.storage
        vps.save(update_fields=["cpu", "ram", "storage"])

    for historical in HistoricalVPS.objects.all().iterator():
        plan = plans.get(historical.plan_id)
        if plan is None:
            continue
        historical.cpu = plan.cpu
        historical.ram = plan.ram
        historical.storage = plan.storage
        historical.save(update_fields=["cpu", "ram", "storage"])
```

- رکوردهای فعلی `VPS` از پلن مرتبط پر می‌شوند.
- رکوردهای تاریخی نیز در حد امکان از پلن مرتبط پر می‌شوند؛ اگر پلن حذف شده باشد مقدار `0` باقی می‌ماند.
- عملیات reverse به‌صورت no-op تعریف شده است، چون حذف فیلدها توسط reverse خود مایگریشن انجام می‌شود.

### ۴-۳. اجرا

```text
Applying vps.0005_vps_hardware_snapshots... OK
makemigrations --check -> No changes detected
```

بررسی داده‌های موجود پس از مایگریشن:

```text
its_vps_name1  16 16 16 | plan: 16 16 16
its_vps_name2  16 16 16 | plan: 16 16 16
its_vps_name22 16 16 16 | plan: 16 16 16
```

---

## ۵. تغییرات سرویس ساخت VPS (`apps/vps/services.py`)

تابع `create_vps_from_order` اکنون به‌جای خواندن از `Plan`، مقادیر اسنپ‌شات سفارش را کپی می‌کند:

```python
vps = VPS.objects.create(
    user=order.user,
    plan=order.plan,
    duration=order.duration,
    operating_system=order.operating_system,
    name=order.vps_name,
    cpu=order.cpu_snapshot,
    ram=order.ram_snapshot,
    storage=order.storage_snapshot,
    # TODO: Replace mock IP/status with Infrastructure Provider
    ip_address="10.10.0.15",
    status=StatusChoices.Active,
)
```

### چرا از `Order` و نه `Plan`؟

`Order` هنگام خرید، مقادیر `cpu_snapshot`، `ram_snapshot` و `storage_snapshot` را ثبت می‌کند. حتی اگر بین ثبت سفارش و پرداخت، پلن تغییر کند، VPS با مشخصات زمان خرید ساخته می‌شود.

نکته: `create_vps_from_order` همچنان idempotent است؛ اگر سفارش از قبل VPS داشته باشد، همان برگردانده می‌شود.

---

## ۶. تغییرات سریالایزرها

### ۶-۱. سریالایزر VPS (`apps/vps/serializers.py`)

`VPSSerializer` از `fields = "__all__"` استفاده می‌کند؛ بنابراین فیلدهای جدید به‌صورت خودکار در پاسخ `GET /api/v1/vps/` قرار می‌گیرند و مقدار آن‌ها از خود مدل `VPS` خوانده می‌شود.

### ۶-۲. سریالایزر VPS داخل سفارش (`apps/orders/serializers.py`)

`OrderVPSDetailSerializer` به‌روزرسانی شد:

```python
class OrderVPSDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = VPS
        fields = [
            "uuid",
            "name",
            "ip_address",
            "status",
            "cpu",
            "ram",
            "storage",
            "plan",
            "duration",
            "operating_system",
            "created_at",
        ]
```

این سریالایزر هم در `OrderDetailSerializer` (فیلد `vps`) و هم در پاسخ اندپوینت پرداخت استفاده می‌شود. بنابراین `cpu`، `ram` و `storage` در سه جا برگردانده می‌شوند:

- `GET /api/v1/vps/`
- `GET /api/v1/orders/<uuid>/` (داخل `vps`)
- `POST /api/v1/orders/<uuid>/pay/` (هم داخل `order.vps` و هم کلید سطح‌بالای `vps`)

---

## ۷. تغییرات ادمین (`apps/vps/admin.py`)

```python
@admin.register(VPS)
class VPSAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'plan',
        'duration',
        'cpu',
        'ram',
        'storage',
        'ip_address',
        'status',
    )
    list_filter = ('status',)
    search_fields = ('user__email', 'plan__name', 'duration__name', 'ip_address')
    readonly_fields = ('cpu', 'ram', 'storage')
```

- `cpu`، `ram` و `storage` در لیست نمایش داده می‌شوند.
- به‌صورت `readonly_fields` تعریف شده‌اند تا از ویرایش دستی اسنپ‌شات خرید جلوگیری شود.

---

## ۸. تست‌ها (`apps/orders/tests.py`)

### ۸-۱. به‌روزرسانی تست‌های موجود

همه فراخوانی‌های مستقیم `VPS.objects.create(...)` در تست‌ها اکنون `cpu`، `ram` و `storage` را نیز مقداردهی می‌کنند.

### ۸-۲. تست‌های جدید/توسعه‌یافته

1. **بررسی اسنپ‌شات در ساخت VPS:**

```python
self.assertEqual(vps.cpu, self.plan.cpu)
self.assertEqual(vps.ram, self.plan.ram)
self.assertEqual(vps.storage, self.plan.storage)
```

2. **تست حفظ منابع پس از تغییر پلن:**

```python
def test_vps_keeps_purchased_hardware_after_plan_changes(self):
    order = self._create_order(vps_name="Snapshot VPS")
    paid_order, _ = process_order_payment(
        user=self.user,
        order_uuid=order.uuid,
    )
    vps = paid_order.vps

    # The plan is edited after purchase; the VPS must keep its snapshot.
    self.plan.cpu = 99
    self.plan.ram = 128
    self.plan.storage = 2048
    self.plan.save(update_fields=["cpu", "ram", "storage"])

    vps.refresh_from_db()
    self.assertEqual(vps.cpu, 2)
    self.assertEqual(vps.ram, 4)
    self.assertEqual(vps.storage, 40)

    client = APIClient()
    client.force_authenticate(user=self.user)

    list_response = client.get("/api/v1/vps/")
    self.assertEqual(list_response.data[0]["cpu"], 2)
    self.assertEqual(list_response.data[0]["ram"], 4)
    self.assertEqual(list_response.data[0]["storage"], 40)

    detail_response = client.get(f"/api/v1/orders/{order.uuid}/")
    self.assertEqual(detail_response.data["vps"]["cpu"], 2)
    self.assertEqual(detail_response.data["vps"]["ram"], 4)
    self.assertEqual(detail_response.data["vps"]["storage"], 40)
```

3. **بررسی حضور فیلدهای سخت‌افزاری در پاسخ پرداخت:**

```python
for field in (
    "uuid",
    "name",
    "ip_address",
    "status",
    "cpu",
    "ram",
    "storage",
    "plan",
    "duration",
    "operating_system",
    "created_at",
):
    self.assertIn(field, response.data["vps"])
```

### ۸-۳. نتیجه اجرا

```text
Found 21 test(s).
System check identified no issues (0 silenced).
.....................
Ran 21 tests in 9.248s

OK
```

بررسی‌های تکمیلی:

```text
manage.py check            -> no issues
makemigrations --check     -> No changes detected
```

---

## ۹. نمونه پاسخ API

### `GET /api/v1/vps/`

```json
[
  {
    "uuid": "...",
    "name": "My VPS",
    "ip_address": "10.10.0.15",
    "status": "active",
    "cpu": 2,
    "ram": 4,
    "storage": 40,
    "plan": "...",
    "duration": "...",
    "operating_system": "...",
    "created_at": "..."
  }
]
```

### `POST /api/v1/orders/<uuid>/pay/` (بخش VPS)

```json
{
  "order": {
    "uuid": "...",
    "status": "active",
    "vps": {
      "uuid": "...",
      "name": "My VPS",
      "ip_address": "10.10.0.15",
      "status": "active",
      "cpu": 2,
      "ram": 4,
      "storage": 40,
      "plan": "...",
      "duration": "...",
      "operating_system": "...",
      "created_at": "..."
    }
  },
  "payment_gateway_response": { "...": "..." },
  "vps": {
    "uuid": "...",
    "name": "My VPS",
    "ip_address": "10.10.0.15",
    "status": "active",
    "cpu": 2,
    "ram": 4,
    "storage": 40,
    "plan": "...",
    "duration": "...",
    "operating_system": "...",
    "created_at": "..."
  }
}
```

اگر پس از این خرید، پلن به `cpu=99`، `ram=128` و `storage=2048` تغییر کند، پاسخ‌های بالا همچنان `cpu=2`، `ram=4` و `storage=40` را نشان می‌دهند.

---

## ۱۰. تصمیم‌های فنی

- **اسنپ‌شات در زمان خرید:** منبع حقیقت برای منابع VPS، مقادیر ثبت‌شده در `Order` است، نه `Plan` لحظه‌ای.
- **فیلدهای غیر nullable:** تضمین می‌کند هر VPS همیشه مشخصات سخت‌افزاری معتبر دارد.
- **مایگریشن دو مرحله‌ای:** افزودن فیلد با default موقت و سپس پر کردن داده، بدون نیاز به حالت nullable و بدون prompt تعاملی.
- **`preserve_default=False`:** جلوگیری از باقی ماندن default در وضعیت نهایی مدل.
- **پشتیبانی از تاریخچه:** فیلدهای جدید در `HistoricalVPS` نیز ثبت می‌شوند تا تغییرات آینده قابل ردیابی باشند.
- **فقط‌خواندنی در ادمین:** جلوگیری از تغییر تصادفی اسنپ‌شات خرید توسط اپراتور.
- **سازگاری API:** فیلدهای جدید در همه مسیرهای خواندن VPS (لیست VPS، جزئیات سفارش و پرداخت) برگردانده می‌شوند.
