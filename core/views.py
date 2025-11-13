from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, View, TemplateView 
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.core.signing import Signer, BadSignature
from .forms import AvailabilityForm, BloqueioForm # 1. Importe o nosso novo formulário
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.core.files.storage import default_storage
from datetime import datetime, time, timedelta
from uuid import uuid4
from .models import BarberService, Appointment, Availability, BarberProfile, Service, Bloqueio
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.throttling import AnonRateThrottle
from .serializers import AppointmentSerializer
from django.utils import timezone
from django.views.generic import DetailView


class AppointmentRateThrottle(AnonRateThrottle):
    """Limita quantos agendamentos anônimos podem ser criados por minuto."""
    rate = '5/min'

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
    model = Availability # O model principal (blocos de horário)
    template_name = 'core/painel_horarios.html'
    context_object_name = 'meus_horarios'

    def get_queryset(self):
        # Busca os blocos de horário (como antes)
        try:
            barber_profile = self.request.user.barber_profile
            return Availability.objects.filter(barber=barber_profile)
        except BarberProfile.DoesNotExist:
            return Availability.objects.none()

    def get_context_data(self, **kwargs):
        # Adiciona TODOS os dados que o painel precisa
        context = super().get_context_data(**kwargs)
        
        if hasattr(self.request.user, 'barber_profile'):
            profile = self.request.user.barber_profile
            context['barber_profile'] = profile
            
            # --- AGENDAMENTOS ---
            hoje = timezone.now().date()
            context['proximos_agendamentos'] = Appointment.objects.filter(
                barber=profile,
                data_hora_inicio__gte=hoje,
                status__in=['pendente', 'confirmado']
            ).order_by('data_hora_inicio')

            # --- FORMULÁRIOS (SÓ ADICIONA SE NÃO VIER DO POST) ---
            if 'availability_form' not in context:
                context['availability_form'] = AvailabilityForm()
            if 'bloqueio_form' not in context:
                context['bloqueio_form'] = BloqueioForm()
                
            # --- LISTA DE BLOQUEIOS (FOLGAS) ---
            context['minhas_folgas'] = Bloqueio.objects.filter(
                barber=profile,
                data_fim__gte=hoje # Só mostra folgas futuras
            ).order_by('data_inicio')
            
        return context

    def post(self, request, *args, **kwargs):
        # Esta função agora precisa de saber QUAL formulário foi enviado.
        # Vamos usar o nome do botão 'submit' para diferenciar.
        
        # Pega o 'profile' ANTES de tudo
        try:
            profile = request.user.barber_profile
        except BarberProfile.DoesNotExist:
            raise PermissionDenied("Perfil de barbeiro não encontrado.")

        context = {} # Contexto para re-renderizar em caso de erro

        # --- Se o formulário de BLOCO DE TRABALHO foi enviado ---
        if 'submit_availability' in request.POST:
            form = AvailabilityForm(request.POST)
            if form.is_valid():
                novo_horario = form.save(commit=False)
                novo_horario.barber = profile
                novo_horario.save()
                return redirect(reverse_lazy('core:painel'))
            else:
                context['availability_form'] = form # Devolve o form com erros

        # --- Se o formulário de BLOQUEIO DE FOLGA foi enviado ---
        elif 'submit_bloqueio' in request.POST:
            form = BloqueioForm(request.POST)
            if form.is_valid():
                nova_folga = form.save(commit=False)
                nova_folga.barber = profile
                nova_folga.save()
                return redirect(reverse_lazy('core:painel'))
            else:
                context['bloqueio_form'] = form # Devolve o form com erros

        # Se deu erro em algum form, re-renderiza a página
        # Chamamos self.get_queryset() para carregar 'meus_horarios'
        self.object_list = self.get_queryset()
        context.update(self.get_context_data(**context))
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
    throttle_classes = [AppointmentRateThrottle]
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
            response_data = AppointmentSerializer(appointment).data
            response_data['success_token'] = Signer().sign(appointment.id)
            return Response(response_data, status=status.HTTP_201_CREATED)
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
    signer = Signer()

    def dispatch(self, request, *args, **kwargs):
        user = request.user

        # Staff/Admin podem visualizar sem token (casos de auditoria)
        if user.is_authenticated and (user.is_superuser or user.is_staff):
            return super().dispatch(request, *args, **kwargs)

        appointment_pk = kwargs.get(self.pk_url_kwarg)
        token = request.GET.get('token')

        if not appointment_pk or not token:
            raise PermissionDenied('Token de acesso obrigatório.')

        try:
            unsigned_pk = self.signer.unsign(token)
        except BadSignature:
            raise PermissionDenied('Token inválido.')

        if str(unsigned_pk) != str(appointment_pk):
            raise PermissionDenied('Token não corresponde a este agendamento.')

        return super().dispatch(request, *args, **kwargs)
    
class GetBarberAvailableDatesView(View):
    """
    Devolve os próximos X dias em que um barbeiro específico
    tem disponibilidade, JÁ EXCLUINDO os dias bloqueados (folgas/férias).
    """
    
    def get(self, request, barber_id):
        start_date = timezone.now().date()
        end_date = start_date + timedelta(days=30) # Range de 30 dias
        
        try:
            barber = BarberProfile.objects.get(pk=barber_id)
        except BarberProfile.DoesNotExist:
            return JsonResponse({'error': 'Barbeiro não encontrado'}, status=404)

        # 1. Encontra os dias da semana em que o barbeiro TRABALHA (ex: [1] para Terça)
        work_weekdays = Availability.objects.filter(
            barber=barber
        ).values_list('dia_da_semana', flat=True).distinct()

        # 2. Busca todos os BLOCOS de folga/férias do barbeiro
        #    que se sobrepõem ao nosso range de 30 dias.
        bloqueios = Bloqueio.objects.filter(
            barber=barber,
            data_inicio__lte=end_date, # O bloqueio começa antes do fim do range
            data_fim__gte=start_date   # E termina depois do início do range
        )
        
        # 3. Cria um set() de datas bloqueadas para checagem rápida
        blocked_dates = set()
        for bloqueio in bloqueios:
            # Itera de 01/12 até 20/12 (exemplo) e adiciona cada dia ao set
            delta = (bloqueio.data_fim - bloqueio.data_inicio).days
            for i in range(delta + 1):
                blocked_dates.add(bloqueio.data_inicio + timedelta(days=i))

        # 4. Gera as datas de trabalho e filtra as bloqueadas
        available_dates = []
        current_date = start_date
        
        while current_date <= end_date:
            # Se o dia da semana é um dia de trabalho (ex: Terça)
            # E este dia específico NÃO está no set de datas bloqueadas
            if current_date.weekday() in work_weekdays and current_date not in blocked_dates:
                available_dates.append(current_date.strftime('%Y-%m-%d'))
                
            current_date += timedelta(days=1)
            
        return JsonResponse({'available_dates': available_dates})
    
class ProfilePhotoUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            profile = request.user.barber_profile
        except BarberProfile.DoesNotExist:
            return Response(
                {'detail': 'Apenas barbeiros podem enviar fotos.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        file_obj = request.FILES.get('photo')
        if not file_obj:
            return Response(
                {'detail': 'Envie um arquivo em "photo".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = f'barber_photos/{uuid4().hex}-{file_obj.name}'
        path = default_storage.save(filename, file_obj)

        profile.profile_picture.name = path
        profile.save(update_fields=['profile_picture'])

        return Response({'photo_url': profile.profile_picture.url}, status=status.HTTP_201_CREATED)

class DeleteBloqueioView(BarberRequiredMixin, View):
    
    def post(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        bloqueio = get_object_or_404(Bloqueio, pk=pk)
        
        # Check de Segurança
        if bloqueio.barber != request.user.barber_profile:
            raise PermissionDenied("Você não tem permissão para deletar este bloqueio.")
            
        bloqueio.delete()
        
        return redirect(reverse_lazy('core:painel'))
