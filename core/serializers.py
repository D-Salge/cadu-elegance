# core/serializers.py
from rest_framework import serializers
from .models import Appointment, BarberService, BarberProfile
from datetime import datetime, timedelta
from django.utils import timezone # Importe o timezone

class AppointmentSerializer(serializers.ModelSerializer):
    """
    Este Serializer valida e cria novos agendamentos.
    """
    
    # --- MUDANÇA AQUI ---
    # O frontend vai enviar o 'service_id' genérico
    service_id = serializers.IntegerField(write_only=True) 
    barber_id = serializers.IntegerField(write_only=True)
    
    start_datetime = serializers.DateTimeField(
        source='data_hora_inicio', 
        format='%Y-%m-%dT%H:%M'
    )
    client_name = serializers.CharField(source='cliente_nome')
    client_phone = serializers.CharField(source='cliente_telefone')

    class Meta:
        model = Appointment
        fields = [
            'id',
            'service_id', # <-- MUDANÇA AQUI
            'barber_id',
            'start_datetime',
            'client_name',
            'client_phone',
        ]

    def validate(self, data):
        """
        Validação customizada: Este é o "guarda" da nossa API.
        """
        
        # --- MUDANÇA AQUI ---
        # 1. Encontra o 'BarberService' usando o service_id e barber_id
        try:
            barber_service = BarberService.objects.get(
                service__id=data['service_id'], # <-- MUDANÇA AQUI
                barber__id=data['barber_id']
            )
        except BarberService.DoesNotExist:
            raise serializers.ValidationError("O serviço ou barbeiro selecionado é inválido.")

        start_time = data['data_hora_inicio']
        end_time = start_time + barber_service.service.duracao

        # 2. O slot já passou?
        # --- MUDANÇA AQUI (para corrigir o bug de timezone) ---
        if start_time < timezone.now():
            raise serializers.ValidationError("Este horário já passou.")

        # 3. O slot está ocupado? (A checagem de colisão)
        existing_appointments = Appointment.objects.filter(
            barber__id=data['barber_id'],
            data_hora_inicio__date=start_time.date(),
            status__in=['pendente', 'confirmado']
        ).filter(
            data_hora_inicio__lt=end_time,
            data_hora_fim__gt=start_time
        )
        
        if existing_appointments.exists():
            raise serializers.ValidationError("Este horário acabou de ser reservado. Por favor, escolha outro.")

        # Adiciona os dados que faltam
        data['barber'] = barber_service.barber
        data['barber_service'] = barber_service
        data['data_hora_fim'] = end_time
        data['status'] = 'pendente'

        return data

    def create(self, validated_data):
        # Remove os IDs que não fazem parte do modelo Appointment
        validated_data.pop('service_id', None) # <-- MUDANÇA AQUI
        validated_data.pop('barber_id', None)
        
        return super().create(validated_data)