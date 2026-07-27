from django import forms

from .models import Adicional, Bebida, Prato


DIA_CHOICES = [
    ("seg", "Segunda"),
    ("ter", "Terca"),
    ("qua", "Quarta"),
    ("qui", "Quinta"),
    ("sex", "Sexta"),
    ("sab", "Sabado"),
    ("dom", "Domingo"),
]


class PratoForm(forms.ModelForm):
    dias_disponiveis = forms.MultipleChoiceField(
        choices=DIA_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Prato
        fields = [
            "nome",
            "descricao",
            "variacoes",
            "imagem",
            "preco",
            "preco_balcao",
            "preco_site",
            "preco_ifood",
            "ativo",
            "dias_disponiveis",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Frango Guisado"}),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Descrição curta para aparecer no cardápio.",
                }
            ),
            "variacoes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Uma por linha. Ex.:\nFraldinha\nFrango",
                }
            ),
            "preco": forms.NumberInput(attrs={"step": "0.01", "placeholder": "24.90"}),
            "preco_balcao": forms.NumberInput(attrs={"step": "0.01", "placeholder": "24.90"}),
            "preco_site": forms.NumberInput(attrs={"step": "0.01", "placeholder": "24.90"}),
            "preco_ifood": forms.NumberInput(attrs={"step": "0.01", "placeholder": "29.90"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound:
            return

        raw_days = ""
        if self.instance and self.instance.pk:
            raw_days = self.instance.dias_disponiveis or ""

        selected = [dia.strip().lower() for dia in raw_days.split(",") if dia.strip()]
        self.initial["dias_disponiveis"] = selected or [value for value, _label in DIA_CHOICES]

    def clean_dias_disponiveis(self):
        selected = self.cleaned_data.get("dias_disponiveis") or []
        valid_order = [value for value, _label in DIA_CHOICES]
        selected_set = set(selected)
        if not selected_set or selected_set == set(valid_order):
            return ""
        return ",".join(value for value in valid_order if value in selected_set)

    def clean_variacoes(self):
        raw = self.cleaned_data.get("variacoes") or ""
        seen = set()
        variations = []
        for line in raw.replace(";", "\n").splitlines():
            value = " ".join(line.strip().split())
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                variations.append(value)
        return "\n".join(variations)


class PratoProntoForm(forms.ModelForm):
    preco_prato_pronto = forms.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=0.01,
        label="Preço no Prato Pronto",
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "22.00"}),
    )
    recorrencia = forms.MultipleChoiceField(
        choices=DIA_CHOICES,
        required=False,
        label="Recorrência",
        widget=forms.CheckboxSelectMultiple,
    )
    ativo_prato_pronto = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = Prato
        fields = ["nome", "descricao", "variacoes", "imagem"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Galinhada"}),
            "descricao": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Descrição curta do prato."}
            ),
            "variacoes": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Uma opção por linha, se houver."}
            ),
        }

    def __init__(self, *args, turno_prato=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.turno_prato = turno_prato
        if self.is_bound:
            return
        if turno_prato:
            self.initial["preco_prato_pronto"] = turno_prato.preco
            selected = list(turno_prato.dias_semana_set)
            self.initial["recorrencia"] = selected or [
                value for value, _label in DIA_CHOICES
            ]
            self.initial["ativo_prato_pronto"] = turno_prato.ativo
        else:
            self.initial["preco_prato_pronto"] = "22.00"
            self.initial["recorrencia"] = [
                value for value, _label in DIA_CHOICES if value != "dom"
            ]

    def clean_recorrencia(self):
        selected = self.cleaned_data.get("recorrencia") or []
        valid_order = [value for value, _label in DIA_CHOICES]
        selected_set = set(selected)
        if not selected_set:
            raise forms.ValidationError("Selecione pelo menos um dia.")
        return ",".join(value for value in valid_order if value in selected_set)

    def clean_variacoes(self):
        raw = self.cleaned_data.get("variacoes") or ""
        seen = set()
        variations = []
        for line in raw.replace(";", "\n").splitlines():
            value = " ".join(line.strip().split())
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                variations.append(value)
        return "\n".join(variations)


class BebidaForm(forms.ModelForm):
    class Meta:
        model = Bebida
        fields = ["nome", "descricao", "imagem", "preco", "preco_balcao", "preco_site", "preco_ifood", "ativo", "ordem"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Coca-Cola 350ml"}),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Descrição curta para aparecer no cardápio.",
                }
            ),
            "preco": forms.NumberInput(attrs={"step": "0.01", "placeholder": "6.00"}),
            "preco_balcao": forms.NumberInput(attrs={"step": "0.01", "placeholder": "6.00"}),
            "preco_site": forms.NumberInput(attrs={"step": "0.01", "placeholder": "6.00"}),
            "preco_ifood": forms.NumberInput(attrs={"step": "0.01", "placeholder": "8.00"}),
            "ordem": forms.NumberInput(attrs={"min": "0", "placeholder": "10"}),
        }


class AdicionalForm(forms.ModelForm):
    class Meta:
        model = Adicional
        fields = ["nome", "descricao", "imagem", "preco", "preco_balcao", "preco_site", "preco_ifood", "ativo", "ordem"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Porcao extra de arroz"}),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Descrição curta para aparecer no cardápio.",
                }
            ),
            "preco": forms.NumberInput(attrs={"step": "0.01", "placeholder": "5.00"}),
            "preco_balcao": forms.NumberInput(attrs={"step": "0.01", "placeholder": "5.00"}),
            "preco_site": forms.NumberInput(attrs={"step": "0.01", "placeholder": "5.00"}),
            "preco_ifood": forms.NumberInput(attrs={"step": "0.01", "placeholder": "7.00"}),
            "ordem": forms.NumberInput(attrs={"min": "0", "placeholder": "10"}),
        }
