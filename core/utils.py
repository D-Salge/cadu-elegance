import requests
import os
from django.conf import settings

def enviar_notificacao_whatsapp_barbeiro(appointment, tipo):
    """
    Simula o envio de uma notificação automática para o barbeiro.
    Em produção, esta função fará um request HTTP para a API do WhatsApp (ex: Twilio/Meta).
    """

    # --- 1. CONSTRUIR A MENSAGEM (Com PII) ---
    # (Esta variável NUNCA deve ser impressa no log)
    barbeiro = appointment.barber.nome_exibicao
    telefone_destino = appointment.barber.clean_whatsapp_phone # Ex: 5534...
    cliente = appointment.cliente_nome
    servico = appointment.barber_service.service.nome
    hora = appointment.data_hora_inicio.strftime('%H:%M')
    data = appointment.data_hora_inicio.strftime('%d/%m')

    mensagem_para_api = "" # Inicializa
    if tipo == 'NOVO':
        mensagem_para_api = (
            f"💈 *Novo Agendamento!* 💈\n\n"
            f"*Cliente:* {cliente}\n"
            f"*Serviço:* {servico}\n"
            f"*Data:* {data} às {hora}\n\n"
            f"Acesse o painel para confirmar."
        )
    elif tipo == 'CANCELAMENTO':
        mensagem_para_api = (
            f"❌ *Agendamento Cancelado* ❌\n\n"
            f"O agendamento de *{cliente}* ({servico}) "
            f"para o dia {data} às {hora} foi cancelado."
        )
    else:
        # Se o tipo for desconhecido, não faz nada
        return

    # --- 2. LOG SEGURO (Sem PII, apenas IDs) ---
    # (Isto é o que vai aparecer no seu terminal)
    
    log_seguro = (
        f"🤖 [WhatsApp Simulado] Gatilho: '{tipo}'. "
        f"Destino: Barbeiro ID {appointment.barber.id}. "
        f"Agendamento ID: {appointment.id}."
    )
    print(log_seguro)

    # --- 3. LÓGICA DE ENVIO REAL (Descomente quando tiver as chaves) ---
    # (O código abaixo só roda se você adicionar as chaves no .env)
    
    # TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    # TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    # TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM') # Ex: whatsapp:+14155238886

    # if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM]):
    #     print("   (Chaves de API não configuradas. Envio real pulado.)")
    #     return

    # api_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    # data_payload = {
    #     'From': TWILIO_WHATSAPP_FROM,
    #     'To': f'whatsapp:{telefone_destino}',
    #     'Body': mensagem_para_api,
    # }

    # try:
    #     response = requests.post(
    #         api_url,
    #         data=data_payload,
    #         auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    #     )
    #     response.raise_for_status() 
    #     print(f"✅ Notificação REAL enviada para {barbeiro}.")
    # except requests.exceptions.RequestException as e:
    #     print(f"❌ ERRO CRÍTICO ao enviar WhatsApp (ID: {appointment.id}): {e}")