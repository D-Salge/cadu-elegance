def enviar_notificacao_whatsapp_barbeiro(appointment, tipo):
    """
    Simula o envio de uma notificação automática para o barbeiro.
    Em produção, esta função faria um request HTTP para a API do WhatsApp (ex: Twilio).
    """
    barbeiro = appointment.barber.nome_exibicao
    telefone = appointment.barber.clean_whatsapp_phone # Já limpo!
    cliente = appointment.cliente_nome
    servico = appointment.barber_service.service.nome
    hora = appointment.data_hora_inicio.strftime('%H:%M')
    data = appointment.data_hora_inicio.strftime('%d/%m')

    if tipo == 'NOVO':
        mensagem_log = f"🤖 NOTIFICAÇÃO WHATSAPP (SIMULADA) PARA {barbeiro} ({telefone}):\n"
        mensagem_log += f"===============================================\n"
        mensagem_log += f"Novo agendamento! Cliente: {cliente}.\n"
        mensagem_log += f"Serviço: {servico} | Data: {data} às {hora}.\n"
        mensagem_log += f"==============================================="
    else:
        mensagem_log = f"STATUS ALTERADO: {tipo} para {barbeiro}."
    
    # Em produção, usarias uma biblioteca como o Twilio para enviar
    # print(f"TWILIO_API.send_message(to='{telefone}', body=mensagem_log)")

    print(mensagem_log) # Mostra no terminal para debug