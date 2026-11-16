# گزارش ساده‌سازی Provider زیرساخت (حذف ABC، Dataclass و OpenStack SDK)

## ۱. خلاصه

در این تغییر، لایه Provider زیرساخت که قبلاً شامل یک کلاس انتزاعی (`ABC`)، dataclass و آداپتور OpenStack بود، به **یک فایل ساده با چند تابع معمولی Python** تبدیل شد که فقط داده‌های Mock تولید می‌کند.

نتیجه:

- حذف کامل `base.py`، `mock.py` و `openstack.py`
- حذف `ABC`، `@dataclass` و کلاس‌ها
- حذف وابستگی به `openstacksdk`
- حذف تنظیمات `INFRASTRUCTURE_PROVIDER` و `OPENSTACK_*`
- فراخوانی مستقیم `create_mock_instance(...)` در تسک Celery

جریان ساخت VPS همچنان غیرهمگام و idempotent باقی مانده است؛ فقط منبع تولید داده Mock ساده‌تر شده است.

---

## ۲. چرا این تغییر انجام شد؟

نسخه قبلی برای یک پروژه آموزشی بیش از حد مهندسی‌شده بود:

1. **کلاس انتزاعی و dataclass** برای یک شبیه‌ساز ساده، پیچیدگی غیرضروری ایجاد می‌کرد.
2. **Factory و تنظیمات سوییچ Provider** در حالی که فقط Mock استفاده می‌شد، کد اضافی و مسیرهای شرطی بی‌مصرف داشت.
3. **وابستگی به `openstacksdk`** فقط برای نگه‌داشتن یک آداپتور بلااستفاده، نصب پکیج سنگین را تحمیل می‌کرد.
4. خواندن و نگهداری چند فایل برای یک رفتار ثابت (تولید UUID و IP ساختگی) دشوارتر بود.

هدف: **سادگی، خوانایی و حذف کد بلااستفاده** بدون تغییر در رفتار بیرونی سیستم.

---

## ۳. ساختار جدید

```text
apps/infrastructure/providers/
└── __init__.py
```

فایل `__init__.py` فقط سه تابع ساده دارد:

```python
import random
import uuid


def create_mock_instance(
    name: str,
    cpu: int,
    ram: int,
    storage: int,
    os_name: str = "",
    region: str = "",
) -> dict:
    """Simulate creating a VPS instance and return mock ID, IP, and status."""
    return {
        "instance_id": f"mock-inst-{uuid.uuid4().hex[:12]}",
        "ip_address": f"10.20.{random.randint(1, 254)}.{random.randint(2, 254)}",
        "status": "ACTIVE",
    }


def delete_mock_instance(instance_id: str) -> bool:
    """Simulate deleting a VPS instance."""
    return True


def get_mock_instance_status(instance_id: str) -> dict:
    """Simulate checking a VPS instance status."""
    return {
        "instance_id": instance_id,
        "status": "ACTIVE",
    }
```

### رفتار توابع

| تابع | خروجی | توضیح |
|---|---|---|
| `create_mock_instance` | `{"instance_id", "ip_address", "status"}` | شناسه `mock-inst-<12 hex>` و IP در بازه `10.20.1-254.2-254` |
| `delete_mock_instance` | `True` | همیشه موفق |
| `get_mock_instance_status` | `{"instance_id", "status": "ACTIVE"}` | وضعیت ثابت |

پارامترهای `name`، `cpu`، `ram`، `storage`، `os_name` و `region` در امضای تابع حفظ شده‌اند تا امضای فراخوانی تسک تغییر نکند و توسعه بعدی آسان باشد؛ اما در Mock استفاده نمی‌شوند.

---

## ۴. تغییرات تسک Celery

فایل: `apps/vps/tasks.py`

### قبل

```python
from apps.infrastructure.providers import get_infrastructure_provider

provider = get_infrastructure_provider()
result = provider.create_instance(**payload)
```

### بعد

```python
from apps.infrastructure.providers import create_mock_instance

result = create_mock_instance(**payload)
```

بقیه منطق تسک بدون تغییر باقی ماند:

1. قفل ردیف سفارش با `select_for_update(of=("self",))`
2. بررسی idempotency (اگر سفارش `active` است یا `provider_instance_id` دارد، خروج)
3. فراخوانی Mock **بیرون از تراکنش**
4. ذخیره `provider_instance_id`، `ip_address` و وضعیت `active`
5. در صورت خطا: `vps.status = "error"` و `order.status = "failed"`

---

## ۵. حذف تنظیمات و وابستگی‌ها

### `cloud_project/settings.py`

بلوک تنظیمات زیر حذف شد:

```python
INFRASTRUCTURE_PROVIDER = ...
OPENSTACK_AUTH_URL = ...
OPENSTACK_USERNAME = ...
OPENSTACK_PASSWORD = ...
OPENSTACK_PROJECT_NAME = ...
OPENSTACK_USER_DOMAIN_NAME = ...
OPENSTACK_PROJECT_DOMAIN_NAME = ...
OPENSTACK_REGION_NAME = ...
OPENSTACK_INTERFACE = ...
OPENSTACK_NETWORK_ID = ...
OPENSTACK_FLAVOR_ID = ...
OPENSTACK_IMAGE_ID = ...
OPENSTACK_TIMEOUT = ...
```

### `.envs/.env.example`

کلیدهای `INFRASTRUCTURE_PROVIDER` و `OPENSTACK_*` حذف شدند.

### `requirements.txt`

```diff
- openstacksdk>=2.0,<4.0
```

از این پس پروژه فقط به Django، DRF و Celery نیاز دارد و نصب آن سبک‌تر است.

---

## ۶. چه چیزهایی تغییر نکرد؟

این ساده‌سازی **رفتار بیرونی** سیستم را تغییر نداده است:

- پرداخت همچنان سفارش را به `provisioning` می‌برد.
- رکورد VPS اولیه با `status="provisioning"`، `ip_address=None` و `provider_instance_id=None` ساخته می‌شود.
- تسک فقط با `transaction.on_commit` صف می‌شود.
- پس از اجرای تسک، VPS و سفارش `active` می‌شوند و IP و شناسه Mock ذخیره می‌شود.
- اجرای دوباره تسک باعث ساخت سرور تکراری نمی‌شود.
- سریالایزرها همان فیلدهای `provider_instance_id`، `ip_address`، `status`، `cpu`، `ram` و `storage` را برمی‌گردانند.

به عبارت دیگر، فقط **پیاده‌سازی داخلی** ساده شده است.

---

## ۷. فایل‌های حذف‌شده

```text
apps/infrastructure/providers/base.py
apps/infrastructure/providers/mock.py
apps/infrastructure/providers/openstack.py
```

## ۸. فایل‌های تغییر‌یافته

```text
apps/infrastructure/providers/__init__.py   (بازنویسی کامل)
apps/vps/tasks.py                           (فراخوانی create_mock_instance)
cloud_project/settings.py                   (حذف تنظیمات Provider/OpenStack)
cloud_project/.envs/.env.example            (حذف کلیدهای Provider/OpenStack)
requirements.txt                            (حذف openstacksdk)
```

---

## ۹. بررسی‌های انجام‌شده

```text
python manage.py check
-> System check identified no issues (0 silenced).
```

جست‌وجوی ارجاع‌های حذف‌شده:

```bash
grep -rn "BaseCloudProvider\|ProvisionedInstance\|MockCloudProvider\|OpenStackCloudProvider\|get_infrastructure_provider" --include='*.py' .
# هیچ نتیجه‌ای ندارد
```

اجرای دستی تسک:

```text
provider     -> {'instance_id': 'mock-inst-85aa881a0456', 'ip_address': '10.20.5.50', 'status': 'ACTIVE'}
status       -> {'instance_id': 'abc', 'status': 'ACTIVE'}
delete       -> True
initial      -> provisioning, None, None
task         -> {'status': 'active', 'instance_id': 'mock-inst-...', 'ip_address': '10.20.x.y'}
final        -> order=active, vps=active, ip=10.20.x.y, provider_instance_id=mock-inst-...
idempotent   -> {'status': 'skipped', 'reason': 'already_provisioned'}
```

> طبق درخواست، هیچ فایل تستی نوشته یا تغییر داده نشد.
