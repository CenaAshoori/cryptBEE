from rest_framework.serializers import Serializer, ModelSerializer, EmailField, CharField, BooleanField, IntegerField, UUIDField
from django.contrib.auth import authenticate
from .models import Two_Factor_Verification, User
from Investments.models import PAN_Verification
from .utils import *
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.hashers import make_password, check_password


class LoginSerializer(Serializer):
    email = EmailField(write_only = True)
    password = CharField(write_only = True)
    two_factor = BooleanField(read_only = True)
    refresh = CharField(read_only = True)
    access = CharField(read_only = True)

    def validate(self,data):
        inemail = normalize_email(data['email'])
        if not User.objects.filter(email = inemail).exists():
            raise CustomError('User not registered')
        user = authenticate(email=inemail, password=data['password'])
        if not user:
            raise CustomError('Invalid Credentials')
        try:
            mobile = Two_Factor_Verification.objects.get(user = user)
            if not mobile.enabled:
                raise ObjectDoesNotExist
            data['two_factor'] = True
            if resend_otp(user, twofactor = True):
                send_two_factor_otp(mobile)
        except ObjectDoesNotExist:
            data['refresh'] = user.refresh
            data['access'] = user.access
            data['two_factor'] = False
        return data


class VerifyTwoFactorOTPSerializer(Serializer):
    email = EmailField(write_only = True)
    otp = IntegerField(write_only = True)
    refresh = CharField(read_only = True)
    access = CharField(read_only = True)

    def validate(self, data):
        user = User.objects.filter(email = normalize_email(data['email']))
        if not user.exists():
            raise CustomError('User not registered')
        user = user[0]
        response = validateOTP(user, data['otp'], twofactoron = True)
        if response == 'OK':
            data['refresh'] = user.refresh
            data['access'] = user.access
            return data
        raise CustomError(response)


class SendOTPEmailSerializer(Serializer):
    email = EmailField()

    def validate(self, data):
        user = User.objects.filter(email = normalize_email(data['email']))
        if not user.exists():
            raise CustomError('User not registered')
        user = user[0]
        if resend_otp(user):
            send_email_otp(user)
        return data


class VerifyOTPEmailSerializer(Serializer):
    email = EmailField()
    otp = IntegerField()

    def validate(self, data):
        user = User.objects.filter(email = normalize_email(data['email']))
        if not user.exists():
            raise CustomError('User not registered')
        user = user[0]
        response = validateOTP(user, data['otp'])
        if response == 'OK':
            return data
        raise CustomError(response)


class ResetPasswordSerializer(Serializer):
    email = EmailField(write_only = True)
    otp = IntegerField(write_only = True)
    password = CharField()

    def validate(self, data):
        if not self.instance.exists():
            raise CustomError('User not registered')
        self.instance = self.instance[0]
        otpresponse = validateOTP(self.instance, data['otp'])
        if not otpresponse == 'OK' :
            raise CustomError('unauthorised access')
        passresponse = validatePASS(data['password'], self.instance.email)
        if not passresponse == 'OK':
            raise CustomError(passresponse)
        validateOTP(self.instance, data['otp'], resetpass = True)
        return data

    def update(self, instance, validated_data):
        instance.password = make_password(validated_data['password'])
        instance.save()
        return instance


class SendLINKEmailSerializer(Serializer):
    email = EmailField()
    password = CharField()

    def validate(self, data):
        inemail = normalize_email(data['email'])
        if User.objects.filter(email =inemail).exists():
            raise CustomError('User with this email already exists')
        response = validatePASS(data['password'])
        if not response == 'OK':
            raise CustomError(response)
        tokenobject = SignUpUser.objects.filter(email = inemail)
        if tokenobject.exists():
            if tokenobject[0].token_generated_at + timedelta(minutes=1) > timezone.now():
                raise CustomError('wait for a minute to send another request')
            tokenobject[0].delete()
        send_email_token(data['password'], inemail)
        return data


class VerifyLINKEmailSerializer(Serializer):
    email = EmailField(required = True)
    token = UUIDField(required = True)
    onapp = BooleanField(required=True)

    def validate(self, data):
        email, token = normalize_email(data['email']), data['token']
        object = SignUpUser.objects.filter(email = email)
        if not object.exists():
            raise CustomError('Invalid Email')
        tempuser = object[0]
        if not token == tempuser.token:
            raise CustomError('Invalid Token')
        if tempuser.token_generated_at + timedelta(minutes=15) < timezone.now():
            tempuser.delete()
            raise CustomError('Link Expired')
        if tempuser.is_verified:
            raise CustomError('Link already used')
        return {**data, **{"object" : tempuser}}

    def create(self, validated_data):
        tempuser = validated_data['object']
        tempuser.is_verified = True
        tempuser.save()
        newuser = User.objects.create_user(
            email = normalize_email(tempuser.email),
            name = tempuser.email.split("@")[0],
            password = tempuser.password
        )
        if validated_data['onapp'] :
            return newuser.tokens()
        return {}


class CheckVerificationSerializer(Serializer):
    is_verified = BooleanField(read_only = True, default = False)
    email = EmailField(write_only = True)
    password = CharField(write_only = True)
    access = CharField(read_only = True)
    refresh = CharField(read_only = True)

    def validate(self, data):
        inemail = normalize_email(data['email'])
        object = SignUpUser.objects.filter(email = inemail)
        if not object.exists():
            raise CustomError('Invalid Email')
        object = object[0]
        if not check_password(data['password'], object.password):
            raise CustomError('Unauthorised access')
        if object.is_verified:
            data['is_verified'] = True
            user = authenticate(email=inemail, password=data['password'])
            data['refresh'] = user.refresh
            data['access'] = user.access
            object.delete()
        return data


class VerifyPANSerializer(ModelSerializer):
    email = EmailField()
    name = CharField(required = False, allow_null = True, default = None)
    
    class Meta:
        model = PAN_Verification
        fields = ['email', 'pan_number', 'name']
        extra_kwargs = {'pan_number': {'required': False, 'allow_null': True, 'default':None}}

    def validate(self, data):
        data['email'] = normalize_email(data['email'])
        user = User.objects.filter(email = data['email'])
        if user.exists():
            if data['pan_number'] is None:
                return data
            if PAN_Verification.objects.filter(user = user[0]).exists():
                raise CustomError('User already verified')
            return data
        raise CustomError('User not registered')
    
    def create(self, validated_data):
        holder = User.objects.get(email = validated_data['email'])
        if validated_data['pan_number'] is not None:
            PAN_Verification(
                user = holder,
                pan_number = validated_data['pan_number']
            ).save()

        if validated_data['name'] is not None:
            holder.name = validated_data['name']
            holder.save()
        return validated_data


class ChangePasswordSerializer(ModelSerializer):
    newpassword = CharField(max_length=128, write_only = True, required = True)

    class Meta:
        model = User
        fields = ['password', 'newpassword']
        extra_kwargs = {'password': {'required': True, 'write_only': True}}

    def validate(self, data):
        if not check_password(data['password'], self.instance.password):
            raise CustomError("Incorrect previous password", code=status.HTTP_406_NOT_ACCEPTABLE)

        if check_password(data['newpassword'], self.instance.password):
            raise CustomError("Password same as previous password", code=status.HTTP_406_NOT_ACCEPTABLE)

        passresponse = validatePASS(data['newpassword'])
        if not passresponse == 'OK':
            raise CustomError(passresponse)

        return data

    def update(self, instance, validated_data):
        instance.password = make_password(validated_data['newpassword'])
        instance.save()
        return validated_data

    def to_representation(self, instance):
        return {'message':['Password changed successfully']}


# class EnableTwoFactorSerializer(Serializer):
#     otp = IntegerField(default = None, write_only=True)

#     class Meta:
#         model = Two_Factor_Verification
#         fields = ['phone_number', 'otp']
#         extra_kwargs = {'phone_number': {'default': None, 'write_only': True}}

#     def validate(self, data):
#         user = self.context['request'].user

#         try:
#             obj = user.twofactor
#             data['create new'] = False
#             data['obj'] = obj
#         except:
#             data['create new'] = True
#             print(data, self.model) 

#             if data['phone_number'] is None:
#                 raise CustomError("phone_number is required")
#             return data

#         if obj.verified:
#             return data

#         if data['otp'] is None or data['phone_number'] is None:
#             raise CustomError("phone_number and otp are required")


#         return data

#     def create(self, validated_data):
#         if validated_data['create new']:
#             obj = self.model.objects.create(
#                 user = self.context['request'].user,
#                 phone_number = validated_data['phone_number']
#             )
#             send_two_factor_otp(obj)

#         obj = validated_data['obj']
#         obj.enabled = True
#         obj.verified = True
#         obj.save()
#         return validated_data


# class DisableTwoFactorSerializer(ModelSerializer):
#     class Meta:
#         model = Two_Factor_Verification
#         fields = [' ']
 
#     def validate(self, attrs):
#         return super().validate(attrs)

#     def create(self, validated_data):
#         return super().create(validated_data)


class ProfilePictureSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ['profile_picture']
        extra_kwargs = {'profile_picture': {'required': True}}


class UserDetailsSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'name', 'profile_picture']

    def to_representation(self, instance):
        data = super().to_representation(instance)

        data['two_factor_verification'] = False
        try:
            obj = instance.twofactor
            if obj.verified:
                if obj.enabled:
                    data['two_factor_verification'] = True
                data['phone_number'] = obj.phone_number
        except:
            pass

        try:
            obj = instance.pan_details
            data['pan_verification'] = True
            data['pan_number'] = obj.pan_number
            data['walltet'] = instance.wallet.amount
        except:
            data['pan_verification'] = False


        return data
