# گزارش پیاده‌سازی محدودیت یکتایی نام VPS در سطح دیتابیس

## ۱. خلاصه

یک محدودیت یکتایی موردی (case-insensitive) روی مدل `VPS` اضافه شده است تا دیتابیس از ایجاد دو VPS با نام یکسان برای یک کاربر جلوگیری کند. در عین حال، کاربران مختلف می‌توانند از نام VPS یکسان استفاده کنند.

این محدودیت در سطح دیتابیس اعمال می‌شود و مستقل از کد اپلیکیشن است؛ بنابراین حتی اگر منطق سرویس دور زده شود یا درخواستی مستقیماً به دیتابیس برسد، نام تکراری رد می‌شود.

---

## ۲. چرا این تغییر لازم بود؟

- **تضمین نهایی در سطح دیتابیس:** اعتبارسنجی در لایه سرویس مفید است، اما تنها لایه دیتابیس می‌تواند در شرایط همزمانی (Race Condition) و درخواست‌های موازی، یکتایی را تضمین کند.
- **جلوگیری از نام‌های تکراری:** هر کاربر باید برای هر VPS نامی یکتا داشته باشد تا شناسایی و مدیریت VPSها ساده و بدون ابهام باشد.
- **عدم حساسیت به حروف:** نام‌هایی مثل `My-VPS` و `my-vps` از نظر کاربر یکسان هستند و نباید هر دو پذیرفته شوند.
- **مجاز بودن نام مشترک بین کاربران:** محدودیت روی ترکیب `(name, user)` است، نه فقط `name`؛ بنابراین دو کاربر مختلف می‌توانند VPS با نام یکسان داشته باشند.
- **پشتیبانی از تاریخچه:** مدل `VPS` از `HistoricalRecords` استفاده می‌کند؛ محدودیت فقط روی جدول اصلی `VPS` اعمال می‌شود و تاریخچه را تحت تأثیر قرار نمی‌دهد.

---

## ۳. تغییر مدل (`apps/vps/models.py`)

### ۳-۱. Importها

```python
from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower
```

### ۳-۲. تعریف محدودیت در `VPS.Meta`

```python
class VPS(AuditModel):
    ...
    history = HistoricalRecords()

    class Meta:
        constraints = [
            UniqueConstraint(
                Lower('name'),
                'user',
                name='unique_vps_name_per_user',
            )
        ]
```

### ۳-۳. توضیح اجزا

| بخش | توضیح |
| --- | --- |
| `Lower('name')` | نام را به حروف کوچک تبدیل می‌کند تا مقایسه بدون حساسیت به حروف باشد. |
| `'user'` | فیلد کلید خارجی کاربر؛ محدودیت را به هر کاربر محدود می‌کند. |
| `name='unique_vps_name_per_user'` | نام ثابت محدودیت برای شناسایی در مایگریشن و دیتابیس. |

### ۳-۴. رفتار نهایی

| سناریو | نتیجه |
| --- | --- |
| `("My-VPS", user_a)` سپس `("my-vps", user_a)` | ❌ رد می‌شود (`IntegrityError`) |
| `("My-VPS", user_a)` سپس `("My-VPS", user_b)` | ✅ مجاز است |
| `("VPS-1", user_a)` سپس `("VPS-2", user_a)` | ✅ مجاز است |

---

## ۴. مایگریشن

### ۴-۱. تولید مایگریشن

دستور اجراشده:

```bash
python manage.py makemigrations vps
```

خروجی:

```text
No changes detected in app 'vps'
```

دلیل: این محدودیت از قبل در مایگریشن موجود ثبت شده است:

`apps/vps/migrations/0004_historicalvps_operating_system_vps_operating_system_and_more.py`

```python
migrations.AddConstraint(
    model_name='vps',
    constraint=models.UniqueConstraint(
        django.db.models.functions.text.Lower('name'),
        models.F('user'),
        name='unique_vps_name_per_user',
    ),
)
```

### ۴-۲. اعمال مایگریشن

دستور اجراشده:

```bash
python manage.py migrate vps
```

خروجی:

```text
Operations to perform:
  Apply all migrations: vps
Running migrations:
  No migrations to apply.
```

### ۴-۳. وضعیت مایگریشن‌ها

```text
vps
 [X] 0001_initial
 [X] 0002_historicalvps_name_vps_name
 [X] 0003_remove_historicalvps_final_price_and_more
 [X] 0004_historicalvps_operating_system_vps_operating_system_and_more
 [X] 0005_vps_hardware_snapshots
```

همه مایگریشن‌ها اعمال شده‌اند و محدودیت در دیتابیس فعال است.

---

## ۵. نحوه کار در عمل

### ۵-۱. ایجاد VPS جدید

هنگام اجرای `VPS.objects.create(...)`، دیتابیس نام را به حروف کوچک تبدیل کرده و با نام‌های موجود همان کاربر مقایسه می‌کند. اگر تکراری باشد، `IntegrityError` پرتاب می‌شود.

```python
from django.db import IntegrityError, transaction

try:
    with transaction.atomic():
        VPS.objects.create(
            user=user,
            plan=plan,
            duration=duration,
            name="My-VPS",
            cpu=2,
            ram=4,
            storage=40,
        )
except IntegrityError:
    # نام تکراری است
    ...
```

### ۵-۲. نکته درباره تراکنش

در Django، وقتی `IntegrityError` رخ می‌دهد، تراکنش جاری نامعتبر می‌شود. بنابراین بهتر است عملیات ساخت VPS داخل یک `transaction.atomic()` داخلی (savepoint) انجام شود تا امکان ادامه کار و مدیریت خطا وجود داشته باشد:

```python
with transaction.atomic():
    try:
        with transaction.atomic():
            VPS.objects.create(...)
    except IntegrityError:
        # مدیریت خطا بدون خراب شدن تراکنش بیرونی
        ...
```

این الگو در لایه سرویس ساخت VPS نیز استفاده می‌شود.

### ۵-۳. رفتار با کاربران مختلف

چون فیلد `user` نیز در محدودیت حضور دارد، نام یکسان برای دو کاربر مختلف مجاز است:

```text
user_a -> "Shared VPS"  ✅
user_b -> "Shared VPS"  ✅
```

---

## ۶. تفاوت با اعتبارسنجی لایه سرویس

| لایه | نقش |
| --- | --- |
| لایه سرویس | بررسی زودهنگام و برگرداندن خطای خوانا (`400`) قبل از رسیدن به دیتابیس |
| لایه دیتابیس | تضمین نهایی یکتایی، حتی در شرایط همزمانی و درخواست‌های موازی |

وجود هر دو لایه توصیه می‌شود:

- لایه سرویس تجربه کاربری بهتری ارائه می‌دهد.
- لایه دیتابیس از صحت داده محافظت می‌کند.

---

## ۷. محدوده تغییرات

طبق درخواست، فقط موارد زیر تغییر کرده‌اند:

- `apps/vps/models.py` (تعریف محدودیت)
- مایگریشن مربوط به `apps/vps` (از قبل موجود و اعمال‌شده)

**هیچ فایل تست یا تست خودکاری نوشته یا تغییر داده نشده است.**

---

## ۸. تصمیم‌های فنی

- **`Lower('name')`:** مقایسه بدون حساسیت به حروف در سطح دیتابیس.
- **ترکیب `(name, user)`:** یکتایی به ازای هر کاربر، نه به‌صورت سراسری.
- **نام ثابت محدودیت:** امکان شناسایی و مدیریت آسان در مایگریشن‌ها و ابزارهای دیتابیس.
- **عدم تأثیر بر `HistoricalVPS`:** تاریخچه تغییرات VPS دست‌نخورده باقی می‌ماند.
- **سازگاری با مایگریشن‌های موجود:** محدودیت در مایگریشن `0004` ثبت شده و نیازی به مایگریشن جدید نیست.
