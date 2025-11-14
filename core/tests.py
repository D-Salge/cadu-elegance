from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from .models import (
    Appointment,
    User,
    BarberProfile,
    Service,
    BarberService,
    Availability,
    Bloqueio,
)
from django.utils import timezone
from datetime import timedelta, time, datetime
from django.core.files.uploadedfile import SimpleUploadedFile
import io
from PIL import Image


class AppointmentAPITests(APITestCase):

    def setUp(self):
        """
        Configura o banco de dados de teste com dados "falsos"
        antes de cada teste rodar.
        """
        # 1. Criar Usuário Barbeiro
        self.barber_user = User.objects.create_user(
            username="testbarber", password="testpassword123", is_barber=True
        )

        # 2. Criar Perfil de Barbeiro
        self.barber_profile = BarberProfile.objects.create(
            user=self.barber_user,
            nome_exibicao="Barbeiro Teste",
            telefone_whatsapp="5511999998888",
        )

        # 3. Criar Serviço
        self.service = Service.objects.create(
            nome="Corte Teste",
            duracao=timedelta(minutes=30),
        )

        # 4. Ligar Serviço ao Barbeiro (com preço)
        self.barber_service = BarberService.objects.create(
            barber=self.barber_profile, service=self.service, preco=50.00
        )

        # 5. Definir disponibilidade (ex: hoje, o dia inteiro)
        hoje_weekday = timezone.now().weekday()  # Pega o dia da semana de hoje
        Availability.objects.create(
            barber=self.barber_profile,
            dia_da_semana=hoje_weekday,
            hora_inicio=time(9, 0),  # 09:00
            hora_fim=time(18, 0),  # 18:00
        )

        # 6. URLs das APIs
        self.create_url = reverse("core:create_appointment")

        # 7. Dados base para o agendamento
        self.base_payload = {
            "barber_id": self.barber_profile.id,
            "service_id": self.service.id,
            "client_name": "Cliente de Teste",
            "client_phone": "11912345678",
        }

    def test_01_create_appointment_success(self):
        """
        Testa se um agendamento válido é criado com sucesso (HTTP 201).
        """
        # Define um horário válido (hoje às 10:00)
        # Usamos 'replace' para garantir que a hora não seja no passado
        valid_time = (timezone.now() + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )

        payload = self.base_payload.copy()
        payload["start_datetime"] = valid_time.isoformat()

        # Força a autenticação (necessário para o CSRF)
        self.client.force_authenticate(user=self.barber_user)

        response = self.client.post(self.create_url, payload, format="json")

        # Verifica se o status code foi 201 (Created)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Verifica se o agendamento realmente foi parar no banco
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Appointment.objects.first().cliente_nome, "Cliente de Teste")

    def test_02_prevent_appointment_collision(self):
        """
        Testa se a API previne uma colisão (booking duplo) no mesmo horário.
        """
        valid_time = (timezone.now() + timedelta(days=1)).replace(
            hour=11, minute=0, second=0, microsecond=0
        )

        payload = self.base_payload.copy()
        payload["start_datetime"] = valid_time.isoformat()

        # Força a autenticação (necessário para o CSRF)
        self.client.force_authenticate(user=self.barber_user)

        # 1. Cria o PRIMEIRO agendamento (deve funcionar)
        response1 = self.client.post(self.create_url, payload, format="json")
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Appointment.objects.count(), 1)  # Agora temos 1 agendamento

        # 2. Tenta criar o SEGUNDO agendamento no mesmo horário
        payload_colisao = payload.copy()
        payload_colisao["client_name"] = "Cliente Atrasado"  # Outro cliente

        response2 = self.client.post(self.create_url, payload_colisao, format="json")

        # Verifica se a API barrou (HTTP 400 Bad Request)
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        # Verifica se o erro foi o que esperamos (do Serializer)
        self.assertIn("Este horário acabou de ser reservado", str(response2.data))
        # Garante que o segundo agendamento NÃO foi salvo
        self.assertEqual(Appointment.objects.count(), 1)

    def test_03_prevent_appointment_on_blocked_day(self):
        """
        Testa se a API (Serializer) previne agendamento em dia de folga (Bloqueio).
        """
        # Define um horário válido para o agendamento (próximo dia às 10:00)
        amanha = timezone.now().date() + timedelta(days=1)
        valid_time = timezone.make_aware(datetime.combine(amanha, time(10, 0)))

        # --- 1. CRIA O BLOQUEIO (FOLGA) ---
        # Bloqueia o dia de amanhã (o dia exato do nosso agendamento)
        Bloqueio.objects.create(
            barber=self.barber_profile,
            data_inicio=amanha,
            data_fim=amanha,
            motivo="Teste de Folga",
        )

        # --- 2. PREPARA O PAYLOAD ---
        payload = self.base_payload.copy()
        payload["start_datetime"] = (
            valid_time.isoformat()
        )  # Tenta agendar no dia bloqueado

        # Força a autenticação (necessário para o CSRF)
        self.client.force_authenticate(user=self.barber_user)

        # --- 3. TENTA CRIAR O AGENDAMENTO ---
        response = self.client.post(self.create_url, payload, format="json")

        # --- 4. VERIFICA O RESULTADO ---
        # Verifica se a API barrou (HTTP 400 Bad Request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Verifica se a mensagem de erro correta (do Serializer) foi enviada
        self.assertIn(
            "O profissional não está disponível nesta data", str(response.data)
        )

        # Garante que NENHUM agendamento foi criado no banco
        self.assertEqual(Appointment.objects.count(), 0)


class SlotGenerationAPITests(APITestCase):

    def setUp(self):
        """Configura um cenário complexo para testar a geração de slots."""

        # --- 1. Definir o dia do teste ---
        # Vamos forçar o teste para ser numa Segunda-feira (weekday=0)
        # Encontra a próxima segunda-feira
        self.test_date = timezone.now().date()
        while self.test_date.weekday() != 0:  # 0 = Segunda-feira
            self.test_date += timedelta(days=1)

        # --- 2. Criar Barbeiro e Serviços ---
        self.barber_user = User.objects.create_user(
            username="barbeiro_slots", password="123", is_barber=True
        )
        self.barber = BarberProfile.objects.create(
            user=self.barber_user, nome_exibicao="Cadu Slots"
        )

        self.servico_30min = Service.objects.create(
            nome="Corte 30min", duracao=timedelta(minutes=30)
        )
        self.servico_90min = Service.objects.create(
            nome="Completo 90min", duracao=timedelta(minutes=90)
        )

        self.bs_30min = BarberService.objects.create(
            barber=self.barber, service=self.servico_30min, preco=50
        )
        self.bs_90min = BarberService.objects.create(
            barber=self.barber, service=self.servico_90min, preco=100
        )

        # --- 3. Criar Disponibilidade (Segunda-feira com pausa p/ almoço) ---
        Availability.objects.create(
            barber=self.barber,
            dia_da_semana=0,  # Segunda-feira
            hora_inicio=time(9, 0),  # 09:00
            hora_fim=time(12, 0),  # 12:00
        )
        Availability.objects.create(
            barber=self.barber,
            dia_da_semana=0,  # Segunda-feira
            hora_inicio=time(14, 0),  # 14:00
            hora_fim=time(17, 0),  # 17:00
        )

        # --- 4. Criar Agendamento (Bloquear um slot) ---
        # Bloqueia o slot das 10:00 às 10:30 na data do teste
        start_dt = timezone.make_aware(datetime.combine(self.test_date, time(10, 0)))
        Appointment.objects.create(
            barber=self.barber,
            barber_service=self.bs_30min,
            cliente_nome="Cliente Fantasma",
            cliente_telefone="123",
            data_hora_inicio=start_dt,
            data_hora_fim=start_dt + timedelta(minutes=30),
            status="confirmado",
        )

        # --- 5. Criar Bloqueio de Férias (para a próxima semana) ---
        self.proxima_segunda = self.test_date + timedelta(days=7)
        Bloqueio.objects.create(
            barber=self.barber,
            data_inicio=self.proxima_segunda,
            data_fim=self.proxima_segunda,
        )

        self.url = reverse("core:get_available_slots")  # A URL da nossa API
        self.url_datas = reverse(
            "core:get_barber_available_dates", kwargs={"barber_id": self.barber.id}
        )

    def test_get_slots_success_and_respects_lunch_break(self):
        """Testa se a API gera os slots corretos e pula o almoço (12:00-14:00)."""

        params = {
            "barber_id": self.barber.id,
            "service_id": self.servico_30min.id,
            "date": self.test_date.strftime("%Y-%m-%d"),
        }
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        slots = response.json().get("available_slots", [])

        # Deve ter os slots da manhã
        self.assertIn("09:00", slots)
        self.assertIn("09:30", slots)
        self.assertIn("11:30", slots)

        # NÃO pode ter slots no almoço
        self.assertNotIn("12:00", slots)
        self.assertNotIn("12:30", slots)
        self.assertNotIn("13:30", slots)

        # Deve ter os slots da tarde
        self.assertIn("14:00", slots)
        self.assertIn("16:30", slots)  # Último slot (16:30-17:00)

    def test_get_slots_respects_existing_appointment(self):
        """Testa se a API remove o slot das 10:00 (que já agendámos no setUp)."""

        params = {
            "barber_id": self.barber.id,
            "service_id": self.servico_30min.id,
            "date": self.test_date.strftime("%Y-%m-%d"),
        }
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        slots = response.json().get("available_slots", [])

        self.assertIn("09:30", slots)  # O das 9:30 deve estar livre
        self.assertNotIn("10:00", slots)  # O das 10:00 deve estar OCUPADO
        self.assertIn("10:30", slots)  # O das 10:30 deve estar livre

    def test_get_slots_respects_service_duration(self):
        """Testa se um serviço de 90min gera menos slots e respeita o fim."""

        params = {
            "barber_id": self.barber.id,
            "service_id": self.servico_90min.id,  # <-- Serviço de 90 min
            "date": self.test_date.strftime("%Y-%m-%d"),
        }
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        slots = response.json().get("available_slots", [])

        # O slot das 10:00 está ocupado (pelo agendamento de 30min)
        # O serviço de 90min (10:30-12:00) colide com o almoço
        self.assertIn("10:30", slots)

        # O último slot da tarde (16:30-18:00) não cabe (só temos até 17:00)
        self.assertIn("15:30", slots)  # 15:30-17:00 (Cabe)
        self.assertNotIn("16:00", slots)  # 16:00-17:30 (Não cabe)

    def test_get_available_dates_filters_blocked_days(self):
        """Testa se a API do CARROSSEL remove o dia de folga (próxima segunda)."""

        response = self.client.get(self.url_datas)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        dates = response.json().get("available_dates", [])

        # A segunda-feira de hoje (dia do teste) DEVE estar na lista
        self.assertIn(self.test_date.strftime("%Y-%m-%d"), dates)

        # A próxima segunda-feira (férias) NÃO PODE estar na lista
        self.assertNotIn(self.proxima_segunda.strftime("%Y-%m-%d"), dates)


class PainelViewTests(TestCase):

    def setUp(self):
        """Configura dois usuários: um barbeiro e um cliente normal."""

        # 1. Criar Barbeiro
        self.barber_user = User.objects.create_user(
            username="barbeiro_painel", password="123", is_barber=True
        )
        self.barber_profile = BarberProfile.objects.create(
            user=self.barber_user, nome_exibicao="Barbeiro Painel"
        )

        # 2. Criar Cliente Normal (não-barbeiro)
        self.client_user = User.objects.create_user(
            username="cliente_normal", password="123"
        )

        self.painel_url = reverse("core:painel")

    # --- Testes de Acesso (Segurança) ---

    def test_01_painel_redirects_anonymous_user_to_login(self):
        """Testa se um usuário não logado é redirecionado para /login."""
        response = self.client.get(self.painel_url)
        # 302 é o código para "Redirecionado"
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f"{reverse('login')}?next={self.painel_url}")

    def test_02_painel_is_forbidden_for_normal_user(self):
        """Testa se um cliente normal (não-barbeiro) recebe 403 Forbidden."""
        self.client.login(username="cliente_normal", password="123")
        response = self.client.get(self.painel_url)
        # 403 é o código para "Acesso Negado/Proibido"
        self.assertEqual(response.status_code, 403)

    def test_03_painel_is_accessible_for_barber(self):
        """Testa se o barbeiro consegue acessar o painel."""
        self.client.login(username="barbeiro_painel", password="123")
        response = self.client.get(self.painel_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/painel_horarios.html")
        self.assertIn(
            "minhas_folgas", response.context
        )  # Verifica se o contexto foi carregado

    # --- Testes de Funcionalidade (Formulários POST) ---

    def test_04_barber_can_add_availability_block(self):
        """Testa se o barbeiro consegue adicionar um novo bloco de trabalho."""
        self.client.login(username="barbeiro_painel", password="123")

        form_data = {
            "dia_da_semana": 0,  # Segunda-feira
            "hora_inicio": "09:00",
            "hora_fim": "12:00",
            "submit_availability": "1",  # O nome do botão que a view espera
        }

        response = self.client.post(self.painel_url, form_data)

        # 302 (Redirect) significa que o POST foi bem-sucedido
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.painel_url)

        # Verifica se o objeto foi realmente criado no banco
        self.assertTrue(
            Availability.objects.filter(
                barber=self.barber_profile, dia_da_semana=0
            ).exists()
        )

    def test_05_barber_can_add_block_off_day(self):
        """Testa se o barbeiro consegue adicionar uma folga (Bloqueio)."""
        self.client.login(username="barbeiro_painel", password="123")

        amanha = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        form_data = {
            "data_inicio": amanha,
            "data_fim": amanha,
            "motivo": "Folga de Teste",
            "submit_bloqueio": "1",  # O nome do botão que a view espera
        }

        response = self.client.post(self.painel_url, form_data)

        # 302 (Redirect) significa que o POST foi bem-sucedido
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, self.painel_url)

        # Verifica se o objeto foi realmente criado no banco
        self.assertTrue(
            Bloqueio.objects.filter(
                barber=self.barber_profile, motivo="Folga de Teste"
            ).exists()
        )

    def test_06_barber_cannot_add_invalid_availability(self):
        """Testa se o formulário de horário (hora fim < hora início) falha."""
        self.client.login(username="barbeiro_painel", password="123")

        form_data = {
            "dia_da_semana": 1,
            "hora_inicio": "14:00",
            "hora_fim": "10:00",  # Erro: Fim antes do Início
            "submit_availability": "1",
        }

        response = self.client.post(self.painel_url, form_data)

        # 200 (OK) significa que a página re-renderizou com um erro de formulário
        self.assertEqual(response.status_code, 200)
        # Verifica se o erro que esperamos (do form.clean()) está no HTML
        self.assertContains(
            response, "A hora de fim deve ser depois da hora de início."
        )


class ProfilePhotoUploadTests(APITestCase):

    def setUp(self):
        # 1. Criar Barbeiro
        self.barber_user = User.objects.create_user(
            username="barbeiro_foto", password="123", is_barber=True
        )
        self.barber_profile = BarberProfile.objects.create(
            user=self.barber_user,
            nome_exibicao="Barbeiro Foto Teste",
            telefone_whatsapp="5511999998888",
        )

        # 2. URL da API
        self.upload_url = reverse("core:profile_photo_upload")

        # 3. Força a autenticação
        self.client.force_authenticate(user=self.barber_user)

    def test_01_upload_photo_success(self):
        """ Testa o upload bem-sucedido de uma imagem pequena. """

        # --- CORREÇÃO: Cria uma imagem PNG real em memória ---
        # (O 'io' cria um arquivo binário em memória)
        img_io = io.BytesIO()
        # Cria uma imagem 100x100, azul
        img = Image.new('RGB', (100, 100), color='blue') 
        # Salva essa imagem como PNG dentro do arquivo em memória
        img.save(img_io, format='PNG')
        img_io.seek(0) # Volta ao início do "arquivo"

        fake_image = SimpleUploadedFile(
            "foto_teste.png", 
            img_io.getvalue(), # <-- Usa o conteúdo PNG real
            content_type="image/png"
        )
        # --- FIM DA CORREÇÃO ---

        response = self.client.post(
            self.upload_url, {"photo": fake_image}, format="multipart"
        )

        # Verifica se o arquivo foi criado (AGORA VAI DAR 201)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verifica se o GCS/Storage retornou um URL
        self.assertIn("photo_url", response.data)

        # Verifica se o perfil no banco foi atualizado
        self.barber_profile.refresh_from_db()
        self.assertTrue(
            self.barber_profile.profile_picture.name.endswith("foto_teste.png")
        )

    def test_02_upload_fails_if_file_too_large(self):
        """Testa se a API bloqueia arquivos maiores que 2MB."""

        # Cria um arquivo 'fake' de 3MB (2MB + 1 byte)
        large_content = b"a" * (2 * 1024 * 1024 + 1)
        fake_large_image = SimpleUploadedFile(
            "foto_grande.jpg", large_content, content_type="image/jpeg"
        )

        response = self.client.post(
            self.upload_url, {"photo": fake_large_image}, format="multipart"
        )

        # A API deve rejeitar (HTTP 400 Bad Request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Verifica se a mensagem de erro do nosso validador está lá
        self.assertIn("O tamanho máximo do arquivo permitido é 2MB", str(response.data))

    def test_03_upload_fails_if_invalid_extension(self):
        """Testa se a API bloqueia arquivos que não são imagens (ex: .txt)."""

        fake_file = SimpleUploadedFile(
            "virus.txt", b"conteudo de texto", content_type="text/plain"
        )

        response = self.client.post(
            self.upload_url, {"photo": fake_file}, format="multipart"
        )

        # A API deve rejeitar (HTTP 400 Bad Request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Verifica se a mensagem de erro do FileExtensionValidator está lá
        self.assertIn("File extension “txt” is not allowed", str(response.data))
