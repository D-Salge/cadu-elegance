from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, View, TemplateView 
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from .forms import AvailabilityForm # 1. Importe o nosso novo formulário
from django.urls import reverse_lazy
from django.http import JsonResponse
from datetime import datetime, time, timedelta
from .models import BarberService, Appointment, Availability, BarberProfile, Service
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import AppointmentSerializer
from django.utils import timezone
from django.views.generic import DetailView

class HomePageView(TemplateView):
    template_name = 'core/homepage.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Busca todos os barbeiros e serviços para o cliente escolher
        context['barbers'] = BarberProfile.objects.all()
        context['services'] = Service.objects.all()
        return context

# ---
# Mixin de Segurança (sem mudanças)
# ---
class BarberRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_barber
    
    def handle_no_permission(self):
        return super().handle_no_permission()

# ---
# A View do Painel (VERSÃO ATUALIZADA)
# ---
class PainelView(BarberRequiredMixin, ListView):
    model = Availability
    template_name = 'core/painel_horarios.html'
    context_object_name = 'meus_horarios'

    def get_queryset(self):
        # (Sem mudanças aqui, continua filtrando por barbeiro logado)
        try:
            barber_profile = self.request.user.barber_profile
            return Availability.objects.filter(barber=barber_profile)
        except BarberProfile.DoesNotExist:
            return Availability.objects.none()

    def get_context_data(self, **kwargs):
        """
        Adiciona dados extras ao template:
        1. O perfil do barbeiro
        2. O formulário de adicionar horário
        3. A lista de próximos agendamentos
        """
        context = super().get_context_data(**kwargs)
        
        # Inicia o formulário (como antes)
        context['form'] = AvailabilityForm()
        
        if hasattr(self.request.user, 'barber_profile'):
            profile = self.request.user.barber_profile
            context['barber_profile'] = profile
            
            # --- NOVO CÓDIGO AQUI ---
            # Busca os próximos agendamentos (pendentes ou confirmados)
            # a partir de hoje
            hoje = timezone.now().date()
            context['proximos_agendamentos'] = Appointment.objects.filter(
                barber=profile,
                data_hora_inicio__gte=hoje,
                status__in=['pendente', 'confirmado']
            ).order_by('data_hora_inicio')
            # --- FIM DO NOVO CÓDIGO ---
            
        return context

    def post(self, request, *args, **kwargs):
        # 3. Este método é chamado quando o formulário é ENVIADO (POST)
        form = AvailabilityForm(request.POST)
        
        if form.is_valid():
            # O formulário é válido!
            # Mas não salve ainda, precisamos ligar ao barbeiro
            novo_horario = form.save(commit=False)
            
            # 4. Pega o perfil do barbeiro logado e liga no formulário
            novo_horario.barber = request.user.barber_profile
            novo_horario.save()
            
            # 5. Redireciona de volta para a mesma página (evita reenvio)
            return redirect(reverse_lazy('core:painel'))
        else:
            # O formulário é inválido (ex: hora final antes da inicial)
            # Renderiza a página novamente, mas com os erros
            context = self.get_context_data() # Pega o contexto (lista de horários)
            context['form'] = form # Passa o formulário preenchido com os erros
            return render(request, self.template_name, context)

class DeleteAvailabilityView(BarberRequiredMixin, View):
    """
    Esta view recebe um POST, checa a permissão e deleta o horário.
    Não usamos a 'DeleteView' padrão do Django porque não queremos
    uma página de confirmação.
    """
    
    def post(self, request, *args, **kwargs):
        # 1. Pega o ID (pk) do horário pela URL
        pk = self.kwargs.get('pk')
        
        # 2. Tenta encontrar o horário no banco de dados
        availability = get_object_or_404(Availability, pk=pk)
        
        # 3. O CHECK DE SEGURANÇA MAIS IMPORTANTE:
        # O horário que ele está tentando deletar pertence
        # ao barbeiro que está logado?
        if availability.barber != request.user.barber_profile:
            # Se não for, é uma tentativa de ataque ou erro.
            # Negamos a permissão.
            raise PermissionDenied("Você não tem permissão para deletar este horário.")
            
        # 4. Se a checagem passou, delete o objeto
        availability.delete()
        
        # 5. Redirecione de volta para o painel
        return redirect(reverse_lazy('core:painel'))
    
# ---
# API VIEW: Para buscar Slots Disponíveis
# ---
class GetAvailableSlotsView(View):
    """
    Esta API View é chamada pelo frontend (JavaScript).
    Ela espera receber 3 parâmetros na URL (Query Params):
    1. barber_id: O ID do BarberProfile
    2. service_id: O ID do Service (serviço genérico)
    3. date: A data que o cliente escolheu (formato AAAA-MM-DD)
    
    Ela retorna um JSON com a lista de slots (horários) disponíveis.
    """

    def get(self, request, *args, **kwargs):
        # 1. Obter os parâmetros da URL
        try:
            barber_id = int(request.GET.get('barber_id'))
            service_id = int(request.GET.get('service_id'))
            selected_date_str = request.GET.get('date')
            
            # Converte a string da data (ex: '2025-11-15') para um objeto date
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            
        except (TypeError, ValueError, AttributeError):
            # Se faltar algum parâmetro ou o formato for inválido
            return JsonResponse({'error': 'Parâmetros inválidos'}, status=400)

        # 2. Encontrar os objetos no banco
        try:
            # Encontra o serviço específico do barbeiro (para pegar a duração e o preço)
            barber_service = BarberService.objects.get(
                barber__id=barber_id, 
                service__id=service_id
            )
            # Pega a duração do serviço (ex: 30 minutos)
            service_duration = barber_service.service.duracao # Este é um objeto timedelta
            
            # Pega o dia da semana (0=Segunda, 1=Terça...)
            weekday = selected_date.weekday()
            
            # Busca TODOS os blocos de disponibilidade daquele barbeiro NAQUELE dia da semana
            # Ex: Bloco 1 (Manhã): 09:00-12:00, Bloco 2 (Tarde): 14:00-18:00
            availability_blocks = Availability.objects.filter(
                barber__id=barber_id, 
                dia_da_semana=weekday
            )
            
            # Busca TODOS os agendamentos já marcados para aquele barbeiro NAQUELA data
            existing_appointments = Appointment.objects.filter(
                barber__id=barber_id,
                data_hora_inicio__date=selected_date,
                status__in=['confirmado', 'pendente'] # Ignora 'cancelado'
            )

        except BarberService.DoesNotExist:
            return JsonResponse({'error': 'Este barbeiro não oferece esse serviço.'}, status=404)
        except Exception as e:
            return JsonResponse({'error': f'Erro ao buscar dados: {e}'}, status=500)

        # --- 3. O ALGORITMO: Gerar e Filtrar os Slots ---
        
        available_slots = []
        
        # Pega os horários dos agendamentos existentes para checagem rápida
        # Usamos 'time()' para comparar só a hora
        booked_slots = {appt.data_hora_inicio.time() for appt in existing_appointments}
        
        # Itera sobre cada bloco de trabalho (ex: manhã, depois tarde)
        for block in availability_blocks:
            
            # Define a hora de início e fim do bloco de trabalho
            # Usamos datetime.combine para juntar a data (ex: 2025-11-15) com a hora (ex: 09:00)
            slot_start_dt = datetime.combine(selected_date, block.hora_inicio)
            block_end_dt = datetime.combine(selected_date, block.hora_fim)
            
            # Itera dentro do bloco, "pulando" de acordo com a duração do serviço
            while slot_start_dt + service_duration <= block_end_dt:
                
                # O horário final do slot
                slot_end_dt = slot_start_dt + service_duration
                
                # Pega a hora atual do slot (ex: 09:00)
                current_time = slot_start_dt.time()
                
                # --- Checagem 1: O slot já está reservado? ---
                if current_time in booked_slots:
                    # Sim, pule para o próximo
                    slot_start_dt += service_duration # Avança o tempo
                    continue # Volta para o início do 'while'
                
                # --- Checagem 2: O slot já passou (para agendamentos no mesmo dia)? ---
                # Compara o 'datetime' do slot com o 'datetime' de agora
                if slot_start_dt < datetime.now():
                    # Sim, pule para o próximo
                    slot_start_dt += service_duration
                    continue
                
                # Se passou nas checagens, é um slot válido!
                available_slots.append(
                    # Formata a hora para o cliente (ex: "09:00")
                    current_time.strftime('%H:%M') 
                )
                
                # Avança o tempo para o próximo slot
                slot_start_dt += service_duration
        
        # 4. Retorna a lista de slots como JSON
        return JsonResponse({'available_slots': available_slots})
    
# ---
# API VIEW (DRF): Para Criar o Agendamento
# ---

# ATENÇÃO: Desabilita o CSRF apenas para esta view.
# Fizemos isso SÓ para testar no Postman sem complicações.
class CreateAppointmentView(APIView):
    """
    Esta API View (DRF) recebe um POST com os dados do cliente
    para criar um novo agendamento.
    """
    
    def post(self, request, *args, **kwargs):
        # 1. Pega os dados brutos (JSON) que o frontend enviou
        data = request.data
        
        # 2. Inicia o nosso Serializer com esses dados
        serializer = AppointmentSerializer(data=data)
        
        # 3. Roda a validação (o método validate() do serializer)
        if serializer.is_valid():
            # Se a validação passou (sem colisão, etc.)
            # o .save() vai chamar o nosso método create()
            appointment = serializer.save()
            
            # 4. Retorna uma resposta de Sucesso (201 Created)
            return Response(
                AppointmentSerializer(appointment).data, 
                status=status.HTTP_201_CREATED
            )
        else:
            # 5. Se a validação falhou, retorna os erros
            # (Ex: "Este horário acabou de ser reservado.")
            return Response(
                serializer.errors, 
                status=status.HTTP_400_BAD_REQUEST
            )

# ---
# View para Confirmar Agendamento
# ---
class ConfirmAppointmentView(BarberRequiredMixin, View):
    
    def post(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        appointment = get_object_or_404(Appointment, pk=pk)
        
        # Check de Segurança: O agendamento é deste barbeiro?
        if appointment.barber != request.user.barber_profile:
            raise PermissionDenied("Você não tem permissão para alterar este agendamento.")
            
        # Altera o status e salva
        appointment.status = 'confirmado'
        appointment.save()
        
        # (Opcional: Enviar E-mail/WhatsApp para o cliente a avisar)
        
        return redirect(reverse_lazy('core:painel'))

# ---
# View para Cancelar Agendamento
# ---
class CancelAppointmentView(BarberRequiredMixin, View):
    
    def post(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        appointment = get_object_or_404(Appointment, pk=pk)
        
        # Check de Segurança
        if appointment.barber != request.user.barber_profile:
            raise PermissionDenied("Você não tem permissão para alterar este agendamento.")
            
        # Altera o status e salva
        appointment.status = 'cancelado'
        appointment.save()
        
        # (Opcional: Enviar E-mail/WhatsApp para o cliente a avisar)
        
        return redirect(reverse_lazy('core:painel'))
    
# ---
# View da Página de Sucesso
# ---
class SuccessPageView(DetailView):
    model = Appointment
    template_name = 'core/success_page.html'
    context_object_name = 'appointment' # Nome do objeto no template