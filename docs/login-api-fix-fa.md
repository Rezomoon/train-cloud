# گزارش اصلاح API ورود (Login)

## ۱. خلاصه

در نسخه قبلی، `LoginUserSerializer` از `ModelSerializer` استفاده می‌کرد و اعتبارسنجی رمز عبور به‌صورت دستی انجام می‌شد. این کار چند مشکل امنیتی و منطقی داشت. در نسخه جدید:

- `LoginUserSerializer` به `serializers.Serializer` ساده تبدیل شد.
- فیلد `password` به‌صورت `write_only` تعریف شد.
- اعتبارسنجی با تابع استاندارد `django.contrib.auth.authenticate` انجام می‌شود.
- `request` از طریق `context` به سریالایزر پاس داده می‌شود.
- پاسخ `LoginView` کامل‌تر و با وضعیت `200 OK` صریح برگردانده می‌شود.

---

## ۲. کد قبلی (مشکل‌دار)

```python
class LoginUserSerializer(ModelSerializer):
    class Meta:
        model = user
        fields = ['mobile', 'password']

    def validate(self, attrs):
        mobile = attrs.get('mobile')
        password = attrs.get('password')

        if mobile and password:
            user_instance = user.objects.filter(mobile=mobile).first()
            if not user_instance or not user_instance.check_password(password):
                raise serializers.ValidationError("Invalid mobile or password.")
            attrs['user'] = user_instance
        else:
            raise serializers.ValidationError("Both mobile and password are required.")
        attrs["user"] = user_instance
        return attrs
```

و در ویو:

```python
serializer = LoginUserSerializer(data=data)
serializer.is_valid(raise_exception=True)
```

---

## ۳. چرا این اتفاق افتاد؟ (ریشه مشکلات)

### ۳-۱. استفاده از `ModelSerializer` برای داده‌ی ورودی

`ModelSerializer` برای ساخت/به‌روزرسانی **مدل** طراحی شده است، نه برای اعتبارسنجی داده‌ی ورودی مثل «ورود». وقتی آن را روی مدل `User` با فیلدهای `mobile` و `password` می‌سازیم:

- فیلد `password` مستقیماً از روی فیلد مدل ساخته می‌شود و به‌طور پیش‌فرض `write_only` نیست؛ یعنی اگر روزی این سریالایزر برای خروجی استفاده شود، ممکن است هش رمز عبور در پاسخ API دیده شود.
- اعتبارسنجی‌های مربوط به مدل (مثل `max_length`) روی ورودی اعمال می‌شود که برای Login بی‌مورد است.
- `create()` و `update()` مدل هم به‌صورت خودکار ساخته می‌شوند که برای Login اصلاً معنا ندارد.

### ۳-۲. اعتبارسنجی دستی رمز عبور

کد قبلی خودش با `filter(mobile=...)` کاربر را پیدا می‌کرد و با `check_password()` رمز را بررسی می‌کرد. این کار منطق احراز هویت جنگو را دور می‌زند و باعث می‌شود:

- وضعیت `is_active` کاربر بررسی نشود (کاربر غیرفعال هم می‌توانست وارد شود).
- بک‌اندهای احراز هویت تنظیم‌شده در `AUTHENTICATION_BACKENDS` نادیده گرفته شوند.
- به‌روزرسانی `last_login` و رفتارهای استاندارد جنگو انجام نشود.
- منطق احراز هویت در دو جای مختلف تکرار و نگهداری آن سخت شود.

### ۳-۳. خط تکراری `attrs["user"] = user_instance`

این خط دو بار نوشته شده بود (یکی داخل `if` و یکی بعد از آن). هرچند خطای اجرایی ایجاد نمی‌کرد، نشانه‌ی کد ناپخته و اضافی بود و خوانایی را کم می‌کرد.

### ۳-۴. پاس داده نشدن `request` به سریالایزر

تابع `authenticate` می‌تواند `request` را دریافت کند و برخی بک‌اندها به آن نیاز دارند. در کد قبلی `context` پاس نمی‌شد، بنابراین در صورت اضافه شدن بک‌اندهای وابسته به request، احراز هویت ناقص می‌شد.

### ۳-۵. پاسخ ناقص ویو

ویو وضعیت HTTP را صریح مشخص نمی‌کرد و اطلاعات کاربر را برنمی‌گرداند. همچنین import بلااستفاده‌ی `AccessToken` وجود داشت.

---

## ۴. کد جدید (اصلاح‌شده)

### ۴-۱. `apps/users/serializers.py`

```python
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from django.contrib.auth import authenticate, get_user_model

user = get_user_model()


class LoginUserSerializer(serializers.Serializer):
    mobile = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        mobile = attrs.get('mobile')
        password = attrs.get('password')

        if not mobile or not password:
            raise serializers.ValidationError("Both mobile and password are required.")

        user_instance = authenticate(
            request=self.context.get('request'),
            username=mobile,
            password=password,
        )
        if user_instance is None:
            raise serializers.ValidationError("Invalid mobile or password.")

        attrs['user'] = user_instance
        return attrs
```

### ۴-۲. `apps/users/api/views.py`

```python
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from apps.users.serializers import LoginUserSerializer, UserCreateSerializer
from rest_framework_simplejwt.tokens import RefreshToken


def generate_main_token(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginUserSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        tokens = generate_main_token(user)

        return Response(
            {
                "message": "Login successful",
                "user": {
                    "id": user.id,
                    "mobile": user.mobile,
                    "role": user.role,
                },
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )
```

---

## ۵. توضیح اصلاحات

| مشکل قبلی | اصلاح انجام‌شده |
|---|---|
| استفاده از `ModelSerializer` برای Login | استفاده از `serializers.Serializer` ساده و صریح |
| احتمال افشای رمز عبور در خروجی | تعریف `password` با `write_only=True` |
| بررسی دستی رمز و نادیده گرفتن `is_active` | استفاده از `authenticate()` استاندارد جنگو |
| نادیده گرفتن بک‌اندهای احراز هویت | `authenticate()` از بک‌اندهای تنظیم‌شده استفاده می‌کند |
| خط تکراری `attrs["user"]` | حذف خط اضافی |
| پاس نشدن `request` | ارسال `context={"request": request}` |
| پاسخ بدون وضعیت صریح و بدون اطلاعات کاربر | برگرداندن `200 OK` همراه با `id`، `mobile` و `role` |

### نکته درباره‌ی `authenticate(username=mobile)`

مدل `User` دارای `USERNAME_FIELD = "mobile"` است. بک‌اند پیش‌فرض جنگو (`ModelBackend`) از همین فیلد برای شناسایی کاربر استفاده می‌کند؛ بنابراین پاس دادن `username=mobile` کاملاً درست است و نیازی به تغییر نام پارامتر نیست.

---

## ۶. رفتار جدید API

### ورود موفق

```bash
curl -X POST http://localhost:8000/users/login/ \
  -H "Content-Type: application/json" \
  -d '{"mobile": "09120000000", "password": "secret123"}'
```

پاسخ:

```json
{
  "message": "Login successful",
  "user": {
    "id": 1,
    "mobile": "09120000000",
    "role": "user"
  },
  "tokens": {
    "access": "...",
    "refresh": "..."
  }
}
```

### اعتبارنامه اشتباه

```json
{
  "non_field_errors": ["Invalid mobile or password."]
}
```

با وضعیت HTTP `400`.

### فیلد خالی

```json
{
  "mobile": ["This field is required."],
  "password": ["This field is required."]
}
```

---

## ۷. نتیجه‌گیری

مشکل اصلی این بود که برای یک عملیات «احراز هویت» از ابزار «سریال‌سازی مدل» استفاده شده بود و منطق احراز هویت به‌صورت دستی و ناقص پیاده‌سازی شده بود. با تبدیل به `Serializer` ساده، استفاده از `authenticate()` و رعایت `write_only` برای رمز عبور، هم امنیت و هم صحت رفتار API بهبود پیدا کرد و کد با استانداردهای جنگو/DRF هم‌راستا شد.
