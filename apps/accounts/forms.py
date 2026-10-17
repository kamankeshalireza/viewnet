from django import forms

from apps.core.text import normalize_phone, to_ascii_digits

from .models import User


class PhoneForm(forms.Form):
    phone = forms.CharField(label="شمارهٔ موبایل", max_length=20,
                            widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel",
                                                          "placeholder": "09123456789", "dir": "ltr"}))

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not phone:
            raise forms.ValidationError("شمارهٔ موبایل را به‌صورت صحیح وارد کنید (مثلاً 09123456789).")
        return phone


class CodeForm(forms.Form):
    code = forms.CharField(label="کد تأیید", max_length=10,
                           widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code",
                                                         "dir": "ltr", "placeholder": "------"}))

    def clean_code(self):
        code = to_ascii_digits(self.cleaned_data["code"]).strip()
        if not (code.isdigit() and len(code) == 6):
            raise forms.ValidationError("کد تأیید ۶ رقم است.")
        return code


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
