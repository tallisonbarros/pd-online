from django import forms

from .models import Bebida, Prato


class PratoForm(forms.ModelForm):
    class Meta:
        model = Prato
        fields = ["nome", "descricao", "imagem", "preco", "ativo", "dias_disponiveis"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Frango Guisado"}),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Descricao curta para aparecer no cardapio.",
                }
            ),
            "preco": forms.NumberInput(attrs={"step": "0.01", "placeholder": "24.90"}),
            "dias_disponiveis": forms.TextInput(
                attrs={"placeholder": "seg,ter,qua ou deixe vazio para todos os dias"}
            ),
        }


class BebidaForm(forms.ModelForm):
    class Meta:
        model = Bebida
        fields = ["nome", "descricao", "imagem", "preco", "ativo", "ordem"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Coca-Cola 350ml"}),
            "descricao": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Descricao curta para aparecer no cardapio.",
                }
            ),
            "preco": forms.NumberInput(attrs={"step": "0.01", "placeholder": "6.00"}),
            "ordem": forms.NumberInput(attrs={"min": "0", "placeholder": "10"}),
        }
