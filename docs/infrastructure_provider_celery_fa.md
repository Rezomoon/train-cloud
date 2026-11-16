# گزارش پیاده‌سازی لایه Provider زیرساخت و ساخت Async ماشین مجازی با Celery

## ۱. خلاصه

در این تغییرات، فرایند ساخت VPS از یک مسیر همگام (synchronous) و وابسته به یک IP ساختگی، به یک جریان **غیرهمگام (asynchronous)** مبتنی بر **Celery** تبدیل شد. همچنین یک **لایه انتزاعی Provider** در `apps/infrastructure/providers/` اضافه شد که دو پیاده‌سازی دارد:

- `MockCloudProvider` برای توسعه و اجرای بدون شبکه
- `OpenStackCloudProvider` برای اتصال واقعی به OpenStack

انتخاب Provider فقط با متغیر محیطی `INFRASTRUCTURE_PROVIDER` انجام می‌شود و هیچ تغییری در سرویس‌ها یا تسک‌ها لازم نیست.

### جریان کلی

```text
POST /api/v1/orders/<uuid>/pay/
        │
        ▼
process_order_payment()
        │  پرداخت Mock موفق
        ▼
order.status = "provisioning"
ساخت رکورد VPS با status="provisioning" و ip/provider_instance_id = None
        │
        ▼
transaction.on_commit(...)  ← فقط بعد از commit واقعی
        │
        ▼
provision_vps_task.delay(order_uuid)
        │
        ▼
get_infrastructure_provider().create_instance(...)
        │
        ▼
VPS: status="active", ip_address=..., provider_instance_id=...
Order: status="active"
        │
        ▼
GET /api/v1/orders/<uuid>/  یا  GET /api/v1/vps/
(کلاینت با polling تغییر وضعیت را می‌بیند)
```

---

## ۲. چرا این تغییر انجام شد؟

نسخه قبلی هنگام پرداخت، بلافاصله VPS را با IP ثابت `10.10.0.15` می‌ساخت و وضعیت را `active` می‌کرد. این کار سه مشکل داشت:

1. **وابستگی به Mock درون سرویس:** منطق ساخت VPS به یک IP ساختگی گره خورده بود و جایگزینی با OpenStack نیازمند تغییر سرویس بود.
2. **همگام بودن:** اگر ساخت ماشین در OpenStack چند دقیقه طول می‌کشید، درخواست HTTP و تراکنش دیتابیس قفل می‌شد.
3. **عدم شفافیت وضعیت:** کلاینت نمی‌توانست تفاوت بین «در حال ساخت» و «آماده» را ببیند.

اهداف:

- جداسازی کامل کد زیرساخت در `apps/infrastructure/`
- امکان سوییچ بین Mock و OpenStack فقط با `.env`
- اجرای ساخت VPS به‌صورت async و idempotent
- نمایش وضعیت `provisioning → active` از طریق API

---

## ۳. تغییرات مدل‌ها و مایگریشن‌ها

### ۳-۱. `apps/vps/models.py`

**`Plan`**

```python
provider_flavor_id = models.CharField(max_length=100, null=True, blank=True)
```

نگاشت اختیاری Plan به Flavor در Provider (مثلاً OpenStack).

**`StatusChoices`**

```python
class StatusChoices(models.TextChoices):
    PROVISIONING = "provisioning", "Provisioning"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ERROR = "error", "Error"
    TERMINATED = "terminated", "Terminated"
```

**`VPS`**

```python
provider_instance_id = models.CharField(
    max_length=100, null=True, blank=True, db_index=True
)
ip_address = models.GenericIPAddressField(null=True, blank=True)
status = models.CharField(
    max_length=50,
    choices=StatusChoices.choices,
    default=StatusChoices.PROVISIONING,
)
```

- `provider_instance_id` شناسه سرور در OpenStack یا Mock را نگه می‌دارد و ایندکس دارد تا جست‌وجو سریع باشد.
- وضعیت پیش‌فرض `provisioning` است تا هیچ VPS تازه‌ای نادرست `active` نشان داده نشود.

### ۳-۲. `apps/infrastructure/models.py`

**`OperatingSystem`**

```python
provider_image_id = models.CharField(max_length=100, null=True, blank=True)
```

نگاشت اختیاری سیستم‌عامل به Image در Provider.

### ۳-۳. `apps/orders/models.py`

وضعیت‌های سفارش از قبل شامل موارد زیر بودند و بدون تغییر باقی ماندند:

```text
pending_payment, paid, provisioning, active, cancelled, failed
```

### ۳-۴. مایگریشن‌ها

```text
apps/infrastructure/migrations/0002_operatingsystem_provider_image_id.py
apps/vps/migrations/0006_historicalvps_provider_instance_id_and_more.py
```

این مایگریشن‌ها روی دیتابیس اعمال شدند:

```bash
python manage.py migrate --noinput
```

> نکته: چون `VPS` از `simple_history` استفاده می‌کند، فیلد `provider_instance_id` به‌صورت خودکار به `HistoricalVPS` هم اضافه شد.

---

## ۴. لایه Provider زیرساخت

ساختار پوشه:

```text
apps/infrastructure/providers/
├── __init__.py      # Factory
├── base.py          # رابط انتزاعی
├── mock.py          # پیاده‌سازی Mock
└── openstack.py     # آداپتور OpenStack
```

### ۴-۱. رابط انتزاعی — `base.py`

```python
@dataclass
class ProvisionedInstance:
    instance_id: str
    ip_address: str
    status: str


class BaseCloudProvider(ABC):
    @abstractmethod
    def create_instance(self, name, cpu, ram, storage, os_name, region) -> dict: ...

    @abstractmethod
    def delete_instance(self, instance_id) -> bool: ...

    @abstractmethod
    def get_instance_status(self, instance_id) -> dict: ...
```

خروجی استاندارد `create_instance` یک دیکشنری با کلیدهای زیر است:

```python
{"instance_id": "...", "ip_address": "...", "status": "ACTIVE"}
```

### ۴-۲. Mock Provider — `mock.py`

- شناسه ساختگی: `mock-inst-<12 hex>`
- IP ساختگی و واقع‌نما: `10.20.X.Y`
- `delete_instance` همیشه `True`
- `get_instance_status` همیشه `ACTIVE`
- هیچ تماس شبکه‌ای انجام نمی‌شود

### ۴-۳. OpenStack Provider — `openstack.py`

- اتصال با `openstack.connect(...)` از `openstacksdk`
- تمام پارامترها از Django settings خوانده می‌شوند
- `openstack` به‌صورت **lazy** ایمپورت می‌شود؛ بنابراین نبودن SDK مانع اجرای Mock نمی‌شود
- انتخاب Flavor:
  - اگر `OPENSTACK_FLAVOR_ID` تنظیم شده باشد از همان استفاده می‌کند
  - در غیر این صورت بر اساس `cpu/ram/storage` بین Flavorها جست‌وجو می‌کند
- انتخاب Image:
  - `OPENSTACK_IMAGE_ID` یا جست‌وجو بر اساس نام سیستم‌عامل
- پس از ساخت، با `wait_for_server` تا آماده شدن سرور صبر می‌کند و IP را از `server.addresses` استخراج می‌کند

### ۴-۴. Factory — `providers/__init__.py`

```python
def get_infrastructure_provider() -> BaseCloudProvider:
    provider_name = getattr(settings, "INFRASTRUCTURE_PROVIDER", "mock").lower()

    if provider_name == "mock":
        return MockCloudProvider()

    if provider_name == "openstack":
        from apps.infrastructure.providers.openstack import OpenStackCloudProvider
        return OpenStackCloudProvider()

    raise ValueError(...)
```

سرویس‌ها و تسک‌ها فقط این تابع را صدا می‌زنند و از نوع Provider بی‌خبرند.

---

## ۵. تنظیمات و `.env`

در `cloud_project/settings.py` اضافه شد:

```python
INFRASTRUCTURE_PROVIDER = env('INFRASTRUCTURE_PROVIDER', default='mock')

OPENSTACK_AUTH_URL = env('OPENSTACK_AUTH_URL', default='http://localhost:5000/v3')
OPENSTACK_USERNAME = env('OPENSTACK_USERNAME', default='')
OPENSTACK_PASSWORD = env('OPENSTACK_PASSWORD', default='')
OPENSTACK_PROJECT_NAME = env('OPENSTACK_PROJECT_NAME', default='')
OPENSTACK_USER_DOMAIN_NAME = env('OPENSTACK_USER_DOMAIN_NAME', default='Default')
OPENSTACK_PROJECT_DOMAIN_NAME = env('OPENSTACK_PROJECT_DOMAIN_NAME', default='Default')
OPENSTACK_REGION_NAME = env('OPENSTACK_REGION_NAME', default='RegionOne')
OPENSTACK_INTERFACE = env('OPENSTACK_INTERFACE', default='public')
OPENSTACK_NETWORK_ID = env('OPENSTACK_NETWORK_ID', default='')
OPENSTACK_FLAVOR_ID = env('OPENSTACK_FLAVOR_ID', default='')
OPENSTACK_IMAGE_ID = env('OPENSTACK_IMAGE_ID', default='')
OPENSTACK_TIMEOUT = env.int('OPENSTACK_TIMEOUT', default=600)
```

در `.envs/.env.example` نیز همین کلیدها مستند شدند.

### سوییچ به OpenStack

فقط کافی است در `.env`:

```env
INFRASTRUCTURE_PROVIDER=openstack
OPENSTACK_AUTH_URL=https://openstack.example.com/v3
OPENSTACK_USERNAME=...
OPENSTACK_PASSWORD=...
OPENSTACK_PROJECT_NAME=...
OPENSTACK_REGION_NAME=RegionOne
OPENSTACK_NETWORK_ID=...
```

هیچ تغییری در `services.py`، `tasks.py` یا سریالایزرها لازم نیست.

---

## ۶. تغییرات سرویس پرداخت — `apps/orders/services.py`

در مسیر موفق پرداخت:

```python
order.payment_status = PaymentStatusChoices.COMPLETED
order.status = OrderStatusChoices.PROVISIONING
order.paid_at = timezone.now()
order.payment_reference = gateway_response["reference_id"]
order.save(update_fields=[...])

vps = create_provisioning_vps_from_order(order)
order.refresh_from_db()

if vps is not None:
    from apps.vps.tasks import provision_vps_task

    transaction.on_commit(
        lambda: provision_vps_task.delay(str(order.uuid))
    )
```

نکات مهم:

- `order.status` بلافاصله `provisioning` می‌شود، نه `active`.
- رکورد VPS اولیه با `status="provisioning"`، `ip_address=None` و `provider_instance_id=None` ساخته می‌شود.
- سخت‌افزار از **snapshot سفارش** (`cpu_snapshot`, `ram_snapshot`, `storage_snapshot`) گرفته می‌شود، نه از Plan قابل تغییر.
- تسک فقط با `transaction.on_commit` صف می‌شود؛ بنابراین اگر تراکنش rollback شود، هیچ تسکی اجرا نمی‌شود.
- پاسخ HTTP همان `200 OK` است و داده سفارش و VPS با وضعیت `provisioning` برگردانده می‌شود.

### تابع کمکی — `apps/vps/services.py`

```python
def create_provisioning_vps_from_order(order: Order) -> Optional[VPS]:
```

- VPS اولیه را می‌سازد و به `order.vps` وصل می‌کند.
- idempotent است: اگر سفارش از قبل VPS داشته باشد، همان را برمی‌گرداند.
- در صورت برخورد نام تکراری (`IntegrityError`)، سفارش را `failed` می‌کند و `None` برمی‌گرداند.

---

## ۷. تسک Celery — `apps/vps/tasks.py`

```python
@shared_task
def provision_vps_task(order_uuid: str):
    ...
```

### فاز ۱ — قفل و بررسی تکراری

```python
with transaction.atomic():
    order = (
        Order.objects.select_for_update(of=("self",))
        .select_related("plan__data_center__region", "operating_system", "vps")
        .get(uuid=order_uuid)
    )

    if order.status == OrderStatusChoices.ACTIVE or (
        order.vps_id and order.vps.provider_instance_id
    ):
        return {"status": "skipped", "reason": "already_provisioned"}
```

- `select_for_update(of=("self",))` فقط ردیف سفارش را قفل می‌کند و از خطای PostgreSQL روی outer join جلوگیری می‌کند.
- **Idempotency Guard:** اگر سفارش `active` باشد یا VPS از قبل `provider_instance_id` داشته باشد، تسک فوراً خارج می‌شود.

### فاز ۲ — تماس با Provider بیرون از قفل

```python
try:
    provider = get_infrastructure_provider()
    result = provider.create_instance(**payload)
except Exception as exc:
    ...
```

تماس شبکه‌ای **بیرون از `transaction.atomic()`** انجام می‌شود تا تأخیر OpenStack باعث قفل طولانی ردیف دیتابیس نشود.

### فاز ۳ — ذخیره نتیجه

```python
with transaction.atomic():
    vps = VPS.objects.select_for_update().get(pk=vps_id)
    order = Order.objects.select_for_update().get(uuid=order_uuid)

    if order.status == OrderStatusChoices.ACTIVE or vps.provider_instance_id:
        return {"status": "skipped", "reason": "already_provisioned"}

    vps.provider_instance_id = result["instance_id"]
    vps.ip_address = result["ip_address"]
    vps.status = StatusChoices.ACTIVE
    vps.save(...)

    order.status = OrderStatusChoices.ACTIVE
    order.save(...)
```

### مدیریت خطا

در صورت خطا در Provider:

- `vps.status = "error"`
- `order.status = "failed"`

بنابراین کلاینت با polling می‌تواند شکست را تشخیص دهد.

---

## ۸. سریالایزرها و API

### `apps/vps/serializers.py`

`VPSSerializer` اکنون فیلدهای زیر را برمی‌گرداند:

```text
uuid, name, user, plan, duration, operating_system,
provider_instance_id, ip_address, status,
cpu, ram, storage, created_at, updated_at
```

### `apps/orders/serializers.py`

`OrderVPSDetailSerializer` نیز `provider_instance_id` را اضافه کرد:

```text
uuid, name, provider_instance_id, ip_address, status,
cpu, ram, storage, plan, duration, operating_system, created_at
```

### نمونه پاسخ بلافاصله بعد از پرداخت

```json
{
  "order": {
    "status": "provisioning",
    "payment_status": "completed",
    "vps": {
      "status": "provisioning",
      "provider_instance_id": null,
      "ip_address": null,
      "cpu": 2,
      "ram": 4,
      "storage": 40
    }
  }
}
```

### نمونه پاسخ پس از اجرای تسک

```json
{
  "order": {
    "status": "active",
    "vps": {
      "status": "active",
      "provider_instance_id": "mock-inst-ed6aefa6b08f",
      "ip_address": "10.20.126.50",
      "cpu": 2,
      "ram": 4,
      "storage": 40
    }
  }
}
```

کلاینت می‌تواند با polling روی `GET /api/v1/orders/<uuid>/` یا `GET /api/v1/vps/` تغییر وضعیت را ببیند.

---

## ۹. پاک‌سازی تسک قبلی

- تسک قدیمی `provision_vps_task` از `apps/orders/tasks.py` حذف شد و نسخه جدید در `apps/vps/tasks.py` قرار گرفت (مطابق جداسازی مسئولیت‌ها).
- `process_mock_payment_task` اکنون وضعیت را `provisioning` می‌کند و تسک جدید را از `apps.vps.tasks` ایمپورت می‌کند.
- فراخوانی مستقیم `create_vps_from_order` در سرویس پرداخت حذف شد.

---

## ۱۰. فایل‌های تغییر‌یافته و جدید

### جدید

```text
apps/infrastructure/providers/__init__.py
apps/infrastructure/providers/base.py
apps/infrastructure/providers/mock.py
apps/infrastructure/providers/openstack.py
apps/vps/tasks.py
apps/infrastructure/migrations/0002_operatingsystem_provider_image_id.py
apps/vps/migrations/0006_historicalvps_provider_instance_id_and_more.py
docs/infrastructure_provider_celery_fa.md
```

### تغییر‌یافته

```text
apps/vps/models.py
apps/vps/services.py
apps/vps/serializers.py
apps/vps/admin.py
apps/orders/models.py          (وضعیت‌ها از قبل کامل بودند)
apps/orders/services.py
apps/orders/tasks.py
apps/orders/serializers.py
apps/infrastructure/models.py
cloud_project/settings.py
cloud_project/.envs/.env.example
requirements.txt               (افزودن openstacksdk)
```

---

## ۱۱. نحوه اجرا

### ۱) اعمال مایگریشن‌ها

```bash
python manage.py migrate
```

### ۲) اجرای Redis، وب و Celery Worker

```bash
docker compose up -d redis db
python manage.py runserver
celery -A cloud_project worker -l info
```

یا با Docker:

```bash
docker compose up -d
```

### ۳) تست دستی جریان

```bash
# ساخت سفارش
curl -X POST http://localhost:8000/api/v1/orders/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"plan_uuid": "...", "duration_uuid": "...", "vps_name": "My VPS"}'

# پرداخت
curl -X POST http://localhost:8000/api/v1/orders/<ORDER_UUID>/pay/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"

# polling وضعیت
curl http://localhost:8000/api/v1/orders/<ORDER_UUID>/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

---

## ۱۲. تصمیم‌های فنی

1. **جداسازی کامل کد زیرساخت:** هیچ importی از `openstack` یا منطق Provider در `apps/orders` یا `apps/vps` وجود ندارد؛ فقط Factory صدا زده می‌شود.
2. **Idempotency دو مرحله‌ای:** هم قبل از تماس با Provider و هم بعد از آن، وضعیت بررسی می‌شود تا اجرای دوباره تسک باعث ساخت سرور تکراری نشود.
3. **قفل کوتاه:** تماس شبکه‌ای بیرون از تراکنش انجام می‌شود؛ در نتیجه تأخیر Provider باعث قفل طولانی ردیف سفارش نمی‌شود.
4. **`transaction.on_commit`:** تسک فقط پس از commit موفق پرداخت صف می‌شود؛ در صورت rollback هیچ تسکی اجرا نمی‌شود.
5. **Lazy import برای OpenStack SDK:** پروژه با Provider Mock حتی بدون نصب `openstacksdk` اجرا می‌شود.
6. **Snapshot سخت‌افزار:** مقادیر `cpu/ram/storage` از سفارش خوانده می‌شوند تا تغییر بعدی Plan روی VPSهای موجود اثر نگذارد.
7. **وضعیت پیش‌فرض `provisioning`:** هیچ VPS تازه‌ای قبل از تأیید Provider به‌اشتباه `active` نمایش داده نمی‌شود.

---

## ۱۳. بررسی‌های انجام‌شده

```text
python manage.py check
-> System check identified no issues (0 silenced).

python manage.py makemigrations --check --dry-run
-> No changes detected

python manage.py migrate --noinput
-> Applying infrastructure.0002_operatingsystem_provider_image_id... OK
-> Applying vps.0006_historicalvps_provider_instance_id_and_more... OK
```

اجرای دستی تسک با Mock Provider:

```text
initial      -> provisioning, None, None
provider     -> {'instance_id': 'mock-inst-...', 'ip_address': '10.20.x.y', 'status': 'ACTIVE'}
task         -> {'status': 'active', 'instance_id': 'mock-inst-...', 'ip_address': '10.20.x.y'}
final        -> order=active, vps=active, ip=10.20.x.y, provider_instance_id=mock-inst-...
idempotent   -> {'status': 'skipped', 'reason': 'already_provisioned'}
```

> طبق درخواست، هیچ فایل تستی نوشته یا تغییر داده نشد.
