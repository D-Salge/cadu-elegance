from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Appointment
from .utils import enviar_notificacao_whatsapp_barbeiro # Função que criaremos

# O 'receiver' é o que escuta o sinal
@receiver(post_save, sender=Appointment)
def notificar_barbeiro_novo_agendamento(sender, instance, created, **kwargs):
    """
    Acionado após um objeto Appointment ser salvo no banco de dados.
    """
    if created and instance.barber:
        # Só envia a notificação se for a CRIAÇÃO de um novo agendamento
        enviar_notificacao_whatsapp_barbeiro(instance, tipo='NOVO')
    
    # Se fosse necessário, poderíamos adicionar um 'elif' para updates de status
    # elif instance.status == 'cancelado':
    #     enviar_notificacao_whatsapp_barbeiro(instance, tipo='CANCELAMENTO')