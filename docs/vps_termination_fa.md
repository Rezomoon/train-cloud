# گزارش پیاده‌سازی درخواست حذف VPS (Termination)

## ۱. خلاصه

در این تغییرات، قابلیت درخواست حذف VPS به‌صورت غیرهمگام (asynchronous) پیاده‌سازی شد. کاربر مالک VPS می‌تواند با یک درخواست `POST` فرایند حذف را آغاز کند؛ وضعیت VPS بلافاصله به `terminating` تغییر می‌کند و یک تسک Celery پس از commit تراکنش، حذف واقعی ماشین در Provider را انجام می‌دهد و در نهایت وضعیت را به `terminated` می‌رساند.

### جریان کلی

```text
POST /api/v1/vps/<uuid>/terminate/
        │
        ▼
TerminateVPSAPIView  (IsAuthenticated)
        │
        ▼
request_vps_termination(user, vps_uuid)
        │  select_for_update + بررسی مالکیت
        │  بررسی وضعیت فعلی
        ▼
vps.status = "terminating"  →  ذخیره
        │
        ▼
transaction.on_commit(...)   ← فقط بعد از commit موفق
        │
        ▼
terminate_vps_task.delay(vps_uuid)
        │
        ▼
delete_mock_instance(provider_instance_id)   ← بیرون از قفل دیتابیس
        │
        ▼
vps.status = "terminated", vps.ip_address = None
        │
        ▼
پاسخ اولیه HTTP 202 با status="terminating"
(کلاینت با polling روی GET /api/v1/vps/<uuid>/ نتیجه نهایی را می‌بیند)
```

---

## ۲. چرا این تغییر انجام شد؟

1. **حذف ماشین ممکن است زمان‌بر باشد:** اگر فراخوانی Provider (مثلاً OpenStack) همگام انجام شود، درخواست HTTP و تراکنش دیتابیس مدت زیادی قفل می‌ماند. بنابراین حذف به Celery سپرده شد.
2. **شفافیت وضعیت برای کاربر:** کاربر باید تفاوت بین «در حال حذف» (`terminating`) و «حذف‌شده» (`terminated`) را ببیند.
3. **جلوگیری از درخواست‌های تکراری:** با قفل ردیف (`select_for_update`) و بررسی وضعیت، دو درخواست هم‌زمان نمی‌توانند دو تسک حذف را صف کنند.
4. **Idempotency:** اگر تسک دوباره اجرا شود (retry یا اجرای دستی)، برای VPS حذف‌شده کاری انجام نمی‌دهد.
5. **آزادسازی IP:** پس از حذف، مرجع IP از رکورد VPS پاک می‌شود تا IP به‌اشتباه در اختیار VPS حذف‌شده باقی نماند.

---

## ۳. تغییرات مدل و مایگریشن

### ۳-۱. `apps/vps/models.py`

به `StatusChoices` وضعیت جدید `terminating` اضافه شد:

```python
class StatusChoices(models.TextChoices):
    PROVISIONING = "provisioning", "Provisioning"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ERROR = "error", "Error"
    TERMINATING = "terminating", "Terminating"
    TERMINATED = "terminated", "Terminated"
```

وضعیت `terminated` از قبل وجود داشت. افزودن `terminating` باعث می‌شود کاربر بتواند «در حال حذف» را از «حذف‌شده» تشخیص دهد.

### ۳-۲. مایگریشن

```text
apps/vps/migrations/0007_alter_historicalvps_status_alter_vps_status.py
```

چون `VPS` از `simple_history` استفاده می‌کند، تغییر choices به‌صورت خودکار روی `HistoricalVPS` هم اعمال شد.

اجرا:

```bash
python manage.py makemigrations vps
python manage.py migrate vps --noinput
```

---

## ۴. منطق سرویس — `apps/vps/services.py`

```python
TERMINABLE_STATUSES = [
    StatusChoices.ACTIVE,
    StatusChoices.INACTIVE,
    StatusChoices.ERROR,
]


def request_vps_termination(user, vps_uuid) -> VPS:
    ...
```

مراحل داخل `with transaction.atomic():`:

1. **دریافت و قفل ردیف با بررسی مالکیت:**

   ```python
   vps = VPS.objects.select_for_update().get(uuid=vps_uuid, user=user)
   ```

   اگر VPS وجود نداشته باشد یا متعلق به کاربر دیگری باشد، `NotFound` (پاسخ `404`) برگردانده می‌شود. این کار عمداً وجود VPS متعلق به دیگران را افشا نمی‌کند.

2. **اعتبارسنجی وضعیت:**

   | وضعیت فعلی | نتیجه |
   |---|---|
   | `terminated` | `400` — «This VPS is already terminated.» |
   | `terminating` | `400` — «Termination is already in progress for this VPS.» |
   | `provisioning` | `400` — «Cannot terminate a VPS while it is still provisioning.» |
   | `active` / `inactive` / `error` | مجاز است |
   | سایر مقادیر | `400` — پیام عمومی عدم امکان حذف |

3. **تغییر وضعیت و صف‌کردن تسک:**

   ```python
   vps.status = StatusChoices.TERMINATING
   vps.save(update_fields=["status", "updated_at"])

   from apps.vps.tasks import terminate_vps_task

   transaction.on_commit(lambda: terminate_vps_task.delay(str(vps.uuid)))

   return vps
   ```

   ایمپورت تسک به‌صورت **lazy** داخل تابع انجام می‌شود تا وابستگی حلقه‌ای بین `services` و `tasks` ایجاد نشود.

   `transaction.on_commit` تضمین می‌کند اگر تراکنش rollback شود، هیچ تسکی صف نشود.

---

## ۵. تسک Celery — `apps/vps/tasks.py`

```python
@shared_task
def terminate_vps_task(vps_uuid: str):
    ...
```

### فاز ۱ — قفل و بررسی تکراری

```python
with transaction.atomic():
    vps = VPS.objects.select_for_update().get(uuid=vps_uuid)

    if vps.status == StatusChoices.TERMINATED:
        return {"status": "skipped", "reason": "already_terminated"}

    provider_id = vps.provider_instance_id
```

- اگر VPS وجود نداشته باشد: `{"status": "skipped", "reason": "vps_not_found"}`
- اگر از قبل `terminated` باشد: تسک بدون هیچ کاری خارج می‌شود (idempotent).
- شناسه Provider قبل از خروج از تراکنش خوانده می‌شود.

### فاز ۲ — فراخوانی Provider بیرون از قفل

```python
if provider_id:
    from apps.infrastructure.providers import delete_mock_instance

    delete_mock_instance(provider_id)
```

تماس با Provider **بیرون از `transaction.atomic()`** انجام می‌شود تا ردیف دیتابیس در طول تماس شبکه‌ای قفل نماند.

در صورت خطا:

- خطا با `logger.exception` ثبت می‌شود؛
- وضعیت VPS به `error` تغییر می‌کند تا در حالت `terminating` گیر نکند.

### فاز ۳ — نهایی‌سازی وضعیت

```python
with transaction.atomic():
    vps = VPS.objects.select_for_update().get(uuid=vps_uuid)
    vps.status = StatusChoices.TERMINATED
    vps.ip_address = None
    vps.save(update_fields=["status", "ip_address", "updated_at"])
```

- وضعیت نهایی `terminated` می‌شود.
- `ip_address` پاک می‌شود تا مرجع IP آزاد شود.
- `provider_instance_id` حفظ می‌شود تا سابقه شناسه ماشین حذف‌شده باقی بماند.

---

## ۶. API و مسیرها

### ۶-۱. ویو — `apps/vps/api/views.py`

```python
class TerminateVPSAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, vps_id):
        vps = request_vps_termination(user=request.user, vps_uuid=vps_id)
        serializer = VPSSerializer(vps)
        return Response(
            {
                "detail": "VPS termination request accepted.",
                "vps": serializer.data,
            },
            status=status.HTTP_202_ACCEPTED,
        )
```

> توجه: ویوهای این پروژه در `apps/vps/api/views.py` قرار دارند و `apps/vps/urls.py` از همان‌جا ایمپورت می‌کند؛ بنابراین ویو جدید نیز مطابق همین الگو اضافه شد.

### ۶-۲. مسیر — `apps/vps/urls.py`

```python
path("<uuid:vps_id>/terminate/", TerminateVPSAPIView.as_view(), name="vps-terminate"),
```

مسیر کامل:

```text
POST /api/v1/vps/<uuid>/terminate/
```

### نمونه درخواست

```bash
curl -X POST http://localhost:8000/api/v1/vps/<VPS_UUID>/terminate/ \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### نمونه پاسخ موفق — `202 Accepted`

```json
{
  "detail": "VPS termination request accepted.",
  "vps": {
    "uuid": "....",
    "name": "My VPS",
    "status": "terminating",
    "ip_address": "10.20.126.50",
    "provider_instance_id": "mock-inst-ed6aefa6b08f",
    "...": "..."
  }
}
```

### نمونه پاسخ خطا

```json
{"detail": "This VPS is already terminated."}
```

```json
{"detail": "Termination is already in progress for this VPS."}
```

```json
{"detail": "Cannot terminate a VPS while it is still provisioning."}
```

```json
{"detail": "VPS not found."}
```

---

## ۷. فایل‌های تغییر‌یافته و جدید

### تغییر‌یافته

```text
apps/vps/models.py
apps/vps/services.py
apps/vps/tasks.py
apps/vps/api/views.py
apps/vps/urls.py
```

### جدید

```text
apps/vps/migrations/0007_alter_historicalvps_status_alter_vps_status.py
docs/vps_termination_fa.md
```

---

## ۸. تصمیم‌های فنی

1. **قفل ردیف قبل از تغییر وضعیت:** `select_for_update` از رقابت دو درخواست هم‌زمان جلوگیری می‌کند؛ فقط یکی از آن‌ها می‌تواند وضعیت را به `terminating` ببرد.
2. **`transaction.on_commit`:** تسک فقط پس از commit موفق صف می‌شود؛ rollback هیچ تسکی باقی نمی‌گذارد.
3. **Idempotency تسک:** وضعیت `terminated` باعث خروج فوری می‌شود؛ اجرای دوباره تسک بی‌خطر است.
4. **تماس Provider بیرون از قفل:** تأخیر شبکه باعث قفل طولانی ردیف نمی‌شود.
5. **مدیریت خطا:** خطای Provider وضعیت را `error` می‌کند تا VPS در `terminating` گیر نکند.
6. **حذف مرجع IP:** پس از حذف، `ip_address = None` می‌شود.
7. **عدم افشای وجود VPS دیگران:** فیلتر `user=user` باعث می‌شود درخواست برای VPS غیرمالک `404` برگرداند، نه `403`.

---

## ۹. نحوه اجرا و بررسی

```bash
# اعمال مایگریشن
python manage.py migrate

# اجرای Redis، وب و Celery Worker
docker compose up -d redis db
python manage.py runserver
celery -A cloud_project worker -l info
```

### بررسی‌های انجام‌شده

```text
python manage.py check
-> System check identified no issues (0 silenced).

python manage.py migrate vps --noinput
-> Applying vps.0007_alter_historicalvps_status_alter_vps_status... OK
```

بررسی ایمپورت تسک و مسیر:

```text
task: apps.vps.tasks.terminate_vps_task
url:  /api/v1/vps/00000000-0000-0000-0000-000000000000/terminate/
```

### سناریوهای مورد انتظار

| سناریو | نتیجه |
|---|---|
| مالک VPS با وضعیت `active` درخواست حذف می‌دهد | `202`، وضعیت `terminating`، صف‌شدن تسک |
| اجرای تسک | فراخوانی `delete_mock_instance`، وضعیت `terminated`، `ip_address = None` |
| درخواست مجدد روی `terminating` | `400` |
| درخواست روی `terminated` | `400` |
| درخواست روی `provisioning` | `400` |
| درخواست برای VPS کاربر دیگر | `404` |

> طبق درخواست، هیچ فایل تستی نوشته یا تغییر داده نشد.
