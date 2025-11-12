from django import forms
from .models import Availability

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