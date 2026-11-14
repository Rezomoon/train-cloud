from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from django.contrib.auth import authenticate, get_user_model

#
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


class UserCreateSerializer(ModelSerializer):
    class Meta:
        model = user
        fields = ['email', 'mobile', 'role', 'national_id', 'password']
        extra_kwargs = {
            'password': {'write_only': True}
        }

    # def create(self, validated_data):
    #     password = validated_data.pop('password', None)
    #     instance = self.Meta.model(**validated_data)
    #     if password is not None:
    #         instance.set_password(password)
    #     instance.create_user(**validated_data)
        
    #     return instance
    def create(self, validated_data):
        return self.Meta.model.objects.create_user(**validated_data)
