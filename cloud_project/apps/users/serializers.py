
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

#
user = get_user_model()


class UserSerializer(ModelSerializer):
    class Meta:
        model = user
        fields = "__all__"


class UserProfileSerializer(ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=False, validators=[validate_password]
    )

    class Meta:
        model = user
        fields = ['id', 'email', 'mobile', 'national_id', 'role', 'password']
        read_only_fields = ['id', 'role']

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=['password'])
        return instance
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


class RefreshTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate_refresh(self, value):
        try:
            RefreshToken(value)
        except TokenError:
            raise serializers.ValidationError("Invalid or expired refresh token.")
        return value


class UserCreateSerializer(ModelSerializer):
    class Meta:
        model = user
        fields = ['email', 'mobile', 'role', 'national_id', 'password']
        extra_kwargs = {
            'password': {'write_only': True}
        }
    def create(self, validated_data):
        return self.Meta.model.objects.create_user(**validated_data)
