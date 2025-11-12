from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
import re

# --- Model 1: Usuário Customizado ---
class User(AbstractUser):
    is_barber = models.BooleanField('É barbeiro', default=False)

# --- Model 2: Serviços ---
# O serviço genérico. Note que REMOVEMOS O PREÇO DAQUI.
class Service(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True, null=True)
    duracao = models.DurationField('Duração') # Ex: 30 minutos

    def __str__(self):
        return self.nome

    # --- ADICIONA ESTE MÉTODO NOVO ---
    @property
    def friendly_duration(self):
        """
        Transforma o 'timedelta' (ex: 00:30:00) 
        num formato amigável (ex: "30min" ou "1h 30min").
        """
        # Converte a duração total para minutos
        total_minutes = int(self.duracao.total_seconds() / 60)
        
        if total_minutes == 0:
            return "0min"
            
        # Calcula horas e minutos
        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}min")
            
        # Junta as partes (ex: "1h 30min")
        return " ".join(parts)

# --- Model 3: Perfil do Barbeiro ---
class BarberProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='barber_profile'
    )
    nome_exibicao = models.CharField('Nome de Exibição', max_length=100)
    telefone_whatsapp = models.CharField('WhatsApp', max_length=20) # Ex: (34) 99868-6361
    bio = models.TextField(blank=True, null=True)
    servicos_oferecidos = models.ManyToManyField(
        Service,
        through='BarberService',
        related_name='barbeiros'
    )

    def __str__(self):
        return self.nome_exibicao

    # --- ADICIONA ESTE MÉTODO NOVO ---
    @property
    def clean_whatsapp_phone(self):
        """
        Limpa o número de telefone (remove '()', ' ', '-')
        e garante que o código do país (55) está presente.
        """
        if not self.telefone_whatsapp:
            return ""
            
        # Remove tudo o que não for dígito
        clean_phone = re.sub(r'[^\d]', '', self.telefone_whatsapp)
        
        # Remove o '0' inicial se for um DDD (ex: 034...)
        if len(clean_phone) == 12 and clean_phone.startswith('0'):
             clean_phone = clean_phone[1:]
             
        # Se o número já tem o 55 (ex: 5534...), está ok
        if clean_phone.startswith('55') and len(clean_phone) >= 12:
            return clean_phone
            
        # Se for um número normal do Brasil (10 ou 11 dígitos), adiciona o 55
        if len(clean_phone) == 10 or len(clean_phone) == 11:
            return f"55{clean_phone}"

        # Se for um formato desconhecido, retorna o que foi limpo
        return clean_phone

# --- NOVO MODEL (Model 4): O Serviço do Barbeiro (com Preço) ---
# Este é o model "through". É aqui que o preço vive.
class BarberService(models.Model):
    barber = models.ForeignKey(BarberProfile, on_delete=models.CASCADE, related_name='barber_services')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='barber_services')
    preco = models.DecimalField('Preço', max_digits=8, decimal_places=2)

    class Meta:
        # Garante que um barbeiro não cadastre o mesmo serviço duas vezes
        unique_together = ('barber', 'service')
    
    def __str__(self):
        return f"{self.service.nome} por {self.barber.nome_exibicao} - R$ {self.preco}"

# --- Model 5: Disponibilidade do Barbeiro ---
# (Sem mudanças neste model)
class Availability(models.Model):
    DAY_CHOICES = [
        (0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
        (3, 'Quinta-feira'), (4, 'Sexta-feira'), (5, 'Sábado'), (6, 'Domingo'),
    ]
    barber = models.ForeignKey(
        BarberProfile, 
        on_delete=models.CASCADE, 
        related_name='availability'
    )
    dia_da_semana = models.IntegerField('Dia da semana', choices=DAY_CHOICES)
    hora_inicio = models.TimeField('Início')
    hora_fim = models.TimeField('Fim')

    class Meta:
        ordering = ['dia_da_semana', 'hora_inicio']

    def __str__(self):
        return f"{self.barber.nome_exibicao} - {self.get_dia_da_semana_display()}"


# --- Model 6: Agendamento ---
class Appointment(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'), ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'), ('concluido', 'Concluído'),
    ]
    
    # MUDANÇA AQUI: Apontamos para BarberService
    # Assim, com um só campo, sabemos o barbeiro, o serviço e o preço.
    barber_service = models.ForeignKey(
        BarberService, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='appointments'
    )
    
    # Deixamos este campo por redundância e facilidade de filtro.
    # (Poderíamos pegar via 'barber_service.barber', mas isso é mais robusto)
    barber = models.ForeignKey(
        BarberProfile, on_delete=models.SET_NULL, null=True, related_name='appointments'
    )
    
    # Informações do cliente
    cliente_nome = models.CharField('Nome do Cliente', max_length=255)
    cliente_telefone = models.CharField('Telefone do Cliente', max_length=20)

    # O slot exato
    data_hora_inicio = models.DateTimeField('Início do Agendamento')
    data_hora_fim = models.DateTimeField('Fim do Agendamento')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')

    class Meta:
        unique_together = ('barber', 'data_hora_inicio')
        ordering = ['data_hora_inicio']

    def __str__(self):
        if self.barber_service:
            return f"{self.cliente_nome} com {self.barber_service.barber.nome_exibicao} ({self.barber_service.service.nome})"
        return f"{self.cliente_nome} (Serviço Indefinido)"