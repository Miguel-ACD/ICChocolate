from django import forms
from .models import Location, Movement, Presentation, Product, UserProfile


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
    type = forms.ChoiceField(label="Operación", choices=Movement.Type.choices[1:])
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
