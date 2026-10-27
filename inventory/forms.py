from django import forms
from .models import Equivalence, Location, Movement, Presentation, Product, UserProfile


class AliasForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["alias"]
        labels = {"alias": "Alias visible"}

    def clean_alias(self):
        alias = " ".join(self.cleaned_data["alias"].split())
        if len(alias) < 2:
            raise forms.ValidationError("Escribe un alias de al menos dos caracteres.")
        return alias


class MovementForm(forms.Form):
    type = forms.ChoiceField(label="Operación", choices=[choice for choice in Movement.Type.choices if choice[0] in ("COMPRA", "VENTA", "CONSUMO", "MERMA", "TRASLADO")])
    presentation = forms.ModelChoiceField(label="Presentación", queryset=Presentation.objects.none())
    quantity = forms.IntegerField(label="Unidades", min_value=1, max_value=9_000_000_000_000_000_000)
    source = forms.ModelChoiceField(label="Ubicación", queryset=Location.objects.none())
    destination = forms.ModelChoiceField(label="Destino del traslado", queryset=Location.objects.none(), required=False)
    reason = forms.CharField(label="Motivo", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["presentation"].queryset = Presentation.objects.filter(active=True, product__active=True).select_related("product")
        self.fields["source"].queryset = Location.objects.filter(active=True)
        self.fields["destination"].queryset = Location.objects.filter(active=True)

    def clean(self):
        data = super().clean()
        type_ = data.get("type")
        destination = data.get("destination")
        source = data.get("source")
        if type_ == Movement.Type.TRANSFER:
            if not destination or destination == source:
                self.add_error("destination", "Elige una ubicación diferente.")
        elif destination:
            self.add_error("destination", "Solo se usa en traslados.")
        if type_ in (Movement.Type.CONSUMPTION, Movement.Type.WASTE) and not data.get("reason", "").strip():
            self.add_error("reason", "Indica el motivo.")
        return data


class ProductForm(forms.Form):
    code = forms.CharField(label="Código de producto", max_length=40)
    name = forms.CharField(label="Nombre de producto", max_length=150)
    description = forms.CharField(label="Descripción", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    presentation_code = forms.CharField(label="Código de presentación", max_length=40)
    presentation_name = forms.CharField(label="Nombre de presentación", max_length=150)
    unit_description = forms.CharField(label="Una unidad representa", max_length=200)
    content_value = forms.DecimalField(label="Contenido por unidad", max_digits=12, decimal_places=3, min_value=0.001)
    content_unit = forms.ChoiceField(label="Unidad de contenido", choices=Presentation.Unit.choices)

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if Product.objects.filter(code__iexact=code).exists():
            raise forms.ValidationError("Este código ya existe.")
        return code

    def clean_presentation_code(self):
        code = self.cleaned_data["presentation_code"].strip().upper()
        if Presentation.objects.filter(code__iexact=code).exists():
            raise forms.ValidationError("Este código ya existe.")
        return code


class LocationForm(forms.Form):
    code = forms.CharField(label="Código", max_length=40)
    name = forms.CharField(label="Nombre de ubicación", max_length=100)

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if Location.objects.filter(code__iexact=code).exists():
            raise forms.ValidationError("Este código ya existe.")
        return code

class PresentationForm(forms.Form):
    product = forms.ModelChoiceField(label="Producto", queryset=Product.objects.none())
    code = forms.CharField(label="Código de presentación", max_length=40)
    name = forms.CharField(label="Nombre", max_length=150)
    unit_description = forms.CharField(label="Una unidad representa", max_length=200)
    content_value = forms.DecimalField(label="Contenido por unidad", max_digits=12, decimal_places=3, min_value=0.001)
    content_unit = forms.ChoiceField(label="Unidad de contenido", choices=Presentation.Unit.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(active=True)

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if Presentation.objects.filter(code__iexact=code).exists():
            raise forms.ValidationError("Este código ya existe.")
        return code


class EquivalenceForm(forms.Form):
    source = forms.ModelChoiceField(label="Presentación de origen", queryset=Presentation.objects.none())
    target = forms.ModelChoiceField(label="Presentación de destino", queryset=Presentation.objects.none())
    source_units = forms.IntegerField(label="Unidades de origen", min_value=1)
    target_units = forms.IntegerField(label="Unidades de destino", min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active = Presentation.objects.filter(active=True, product__active=True).select_related("product")
        self.fields["source"].queryset = active
        self.fields["target"].queryset = active

    def clean(self):
        data = super().clean()
        source, target = data.get("source"), data.get("target")
        if source and target and source.pk == target.pk:
            self.add_error("target", "Elige una presentación diferente.")
        return data


class ConversionForm(forms.Form):
    equivalence = forms.ModelChoiceField(label="Equivalencia", queryset=Equivalence.objects.none())
    multiples = forms.IntegerField(label="Número de conversiones", min_value=1)
    location = forms.ModelChoiceField(label="Ubicación", queryset=Location.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["equivalence"].queryset = Equivalence.objects.filter(active=True).select_related("source", "target")
        self.fields["location"].queryset = Location.objects.filter(active=True)


class ReversalForm(forms.Form):
    reason = forms.CharField(label="Motivo de la corrección", max_length=500,
                             widget=forms.Textarea(attrs={"rows": 3}))

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("Indica el motivo.")
        return reason


class LocationRenameForm(forms.Form):
    location = forms.ModelChoiceField(label="Ubicación", queryset=Location.objects.none())
    name = forms.CharField(label="Nuevo nombre", max_length=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.all()

class ProductEditForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=150)
    description = forms.CharField(label="Descripción", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    active = forms.BooleanField(label="Activo", required=False)


class PresentationEditForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=150)
    unit_description = forms.CharField(label="Descripción de una unidad", max_length=200)
    active = forms.BooleanField(label="Activa", required=False)


class LocationEditForm(forms.Form):
    name = forms.CharField(label="Nombre", max_length=100)
    active = forms.BooleanField(label="Activa", required=False)

class UserCreateForm(forms.Form):
    email = forms.EmailField(label="Correo de acceso", max_length=150)
    alias = forms.CharField(label="Nombre visible", max_length=40)
    role = forms.ChoiceField(label="Perfil", choices=UserProfile.Role.choices)
    password1 = forms.CharField(label="Contraseña inicial", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Repetir contraseña", widget=forms.PasswordInput)

    def clean_email(self):
        from django.contrib.auth import get_user_model
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email

    def clean(self):
        from django.contrib.auth.password_validation import validate_password
        data = super().clean()
        if data.get("password1") and data.get("password2") and data["password1"] != data["password2"]:
            self.add_error("password2", "Las contraseñas no coinciden.")
        elif data.get("password1"):
            try:
                validate_password(data["password1"])
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data


class UserEditForm(forms.Form):
    alias = forms.CharField(label="Nombre visible", max_length=40)
    role = forms.ChoiceField(label="Perfil", choices=UserProfile.Role.choices)
    active = forms.BooleanField(label="Cuenta activa", required=False)
