from django import forms
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
    )
from .models import User, SuperSign


User = get_user_model()

class UserLoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean(self, *args, **kwargs):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        try:
            u = User.objects.filter(username=username).first()
        except:
            raise forms.ValidationError("This user does not exist")
        if u and password:
            user = authenticate(id=username, password=password)
            if not user or not user.check_password(password):
                raise forms.ValidationError("Incorrect passsword")
            # if not user.is_active:
            #     raise forms.ValidationError("This user is not longer active.")
        return super(UserLoginForm, self).clean(*args, **kwargs)



class UserRegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = [
            'username',
            # 'email',
            'password',
            'password_confirm',
        ]

    def clean_email2(self):
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')
        password_confirm = self.cleaned_data.get('password2')
        if password != password_confirm:
            raise forms.ValidationError("Passwords must match")
        email_qs = User.objects.filter(email=email)
        if email_qs.exists():
            raise forms.ValidationError("This email has already been registered")
        return email


class SuperSignForm(forms.ModelForm):

    class Meta:
        model = SuperSign
        fields = [
            'pointerId',
            'data'
        ]
