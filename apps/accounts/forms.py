from django import forms

from apps.core.text import normalize_phone, to_ascii_digits

from .models import Address, User


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


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["receiver_name", "receiver_phone", "province", "city", "address_line", "plaque", "unit", "postal_code", "is_default"]
        widgets = {"address_line": forms.Textarea(attrs={"rows": 3}),
                   "receiver_phone": forms.TextInput(attrs={"dir": "ltr", "inputmode": "tel"}),
                   "postal_code": forms.TextInput(attrs={"dir": "ltr", "inputmode": "numeric", "maxlength": 10})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.locations.models import City

        province_id = self.data.get("province") or (self.instance.province_id if self.instance.pk else None)
        qs = City.objects.filter(is_active=True)
        self.fields["city"].queryset = qs.filter(province_id=province_id) if str(province_id or "").isdigit() else qs.none()
        for name, f in self.fields.items():
            if name != "is_default":
                f.widget.attrs.setdefault("class", "form-select" if name in ("province", "city") else "form-control")
            else:
                f.widget.attrs["class"] = "form-check-input"

    def clean_receiver_phone(self):
        phone = normalize_phone(self.cleaned_data["receiver_phone"])
        if not phone:
            raise forms.ValidationError("شمارهٔ موبایل گیرنده را صحیح وارد کنید.")
        return phone

    def clean_postal_code(self):
        code = to_ascii_digits(self.cleaned_data["postal_code"]).strip()
        if not (code.isdigit() and len(code) == 10):
            raise forms.ValidationError("کد پستی باید ۱۰ رقم باشد.")
        return code

    def clean(self):
        data = super().clean()
        province, city = data.get("province"), data.get("city")
        if province and city and city.province_id != province.pk:
            self.add_error("city", "این شهر متعلق به استان انتخاب‌شده نیست.")
        return data
