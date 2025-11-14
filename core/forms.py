from datetime import timedelta
from django import forms
from .models import Availability, Bloqueio, Service
from django.utils import timezone


class AvailabilityForm(forms.ModelForm):
    # Usamos TimeInput para que o HTML renderize um campo de hora (HH:MM)
    hora_inicio = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'step': '900'}), # step 900 = incrementos de 15 min
        label="Hora de Início"
    )
    hora_fim = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'step': '900'}),
        label="Hora de Fim"
    )

    class Meta:
        model = Availability
        # Quais campos o barbeiro vai preencher?
        fields = ['dia_da_semana', 'hora_inicio', 'hora_fim']
        labels = {
            'dia_da_semana': 'Dia da Semana',
        }
        
    def clean(self):
        # Chama a lógica de limpeza principal primeiro
        cleaned_data = super().clean() 
        
        hora_inicio = cleaned_data.get("hora_inicio")
        hora_fim = cleaned_data.get("hora_fim")

        # Se ambos os campos existirem, compara-os
        if hora_inicio and hora_fim:
            if hora_fim <= hora_inicio:
                # Se a hora de fim for antes ou igual, levanta um erro
                raise forms.ValidationError(
                    "A hora de fim deve ser depois da hora de início."
                )
        
        return cleaned_data
        
class BloqueioForm(forms.ModelForm):
    # Usamos o DateInput do HTML5 para um calendário
    data_inicio = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Data de Início"
    )
    data_fim = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        label="Data de Fim"
    )

    class Meta:
        model = Bloqueio
        # Campos que o barbeiro vai preencher
        fields = ['data_inicio', 'data_fim', 'motivo']
        labels = {
            'motivo': 'Motivo (Opcional)',
        }

    # Validação para garantir que a data de início não é no passado
    def clean_data_inicio(self):
        data_inicio = self.cleaned_data.get('data_inicio')
        if data_inicio and data_inicio < timezone.now().date():
            raise forms.ValidationError("A data de início não pode ser no passado.")
        return data_inicio

    # Validação para garantir que a data fim não é antes da início
    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')

        if data_inicio and data_fim:
            if data_fim < data_inicio:
                raise forms.ValidationError(
                    "A data de fim não pode ser anterior à data de início."
                )
        return cleaned_data
    
class ServiceForm(forms.ModelForm):
    duracao = forms.CharField(
        label="Duração (HH:MM)",
        widget=forms.TextInput(attrs={'placeholder': 'Ex: 00:30 ou 01:15'}),
        help_text="Tempo médio para este serviço."
    )

    class Meta:
        model = Service
        fields = ['nome', 'descricao', 'duracao']
        labels = {
            'nome': 'Nome do Serviço',
            'descricao': 'Descrição (Opcional)',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Ex: Corte Masculino'}),
            'descricao': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ex: Corte com máquina e tesoura.'}),
        }

    def clean_duracao(self):
        # Converte o input "HH:MM" para um objeto timedelta que o Django entende
        duracao_str = self.cleaned_data.get('duracao')
        try:
            h, m = map(int, duracao_str.split(':'))
            return timedelta(hours=h, minutes=m)
        except (ValueError, TypeError):
            raise forms.ValidationError("Formato inválido. Use HH:MM (ex: 00:45 para 45 min).")