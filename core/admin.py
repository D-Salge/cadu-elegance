from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, Service, BarberProfile, 
    Availability, Appointment, BarberService, Bloqueio
)

# --- Configuração do Admin de Usuário ---
class BarberProfileInline(admin.StackedInline):
    model = BarberProfile
    can_delete = False
    verbose_name_plural = 'Perfil de Barbeiro'
    fk_name = 'user'
    
    fields = ('nome_exibicao', 'telefone_whatsapp', 'bio', 'profile_picture')

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('is_barber',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('is_barber',)}),
    )
    list_display = ('username', 'email', 'is_staff', 'is_barber')
    inlines = (BarberProfileInline, )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('barber_profile')

# --- Configuração dos outros Models ---

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    # MUDANÇA: Removemos o 'preco'
    list_display = ('nome', 'duracao')
    search_fields = ('nome',)

# NOVO INLINE: Para adicionar serviços E preços dentro do Barbeiro
class BarberServiceInline(admin.TabularInline):
    model = BarberService
    # O 'autocomplete_fields' ajuda a buscar o serviço pelo nome
    autocomplete_fields = ('service',) 
    extra = 1

class AvailabilityInline(admin.TabularInline):
    model = Availability
    extra = 1

@admin.register(BarberProfile)
class BarberProfileAdmin(admin.ModelAdmin):
    list_display = ('nome_exibicao', 'user', 'telefone_whatsapp')
    search_fields = ('nome_exibicao', 'user__username')
    # MUDANÇA: Adicionamos os dois inlines
    inlines = (BarberServiceInline, AvailabilityInline,)
    
    # Precisamos disso para o autocomplete_fields funcionar
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Garante que o usuário só possa se ver
        return form

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    # MUDANÇA: 'service' -> 'barber_service'
    list_display = ('cliente_nome', 'barber', 'barber_service', 'data_hora_inicio', 'status')
    list_filter = ('status', 'barber', 'data_hora_inicio')
    search_fields = ('cliente_nome', 'barber__nome_exibicao')
    readonly_fields = ('data_hora_fim',)
    # Adiciona busca fácil pelo serviço/barbeiro
    autocomplete_fields = ('barber_service', 'barber')

# --- Registros Finais ---
admin.site.register(User, CustomUserAdmin)

# Precisamos registrar o BarberService para o autocomplete funcionar
@admin.register(BarberService)
class BarberServiceAdmin(admin.ModelAdmin):
    list_display = ('barber', 'service', 'preco')
    search_fields = ('barber__nome_exibicao', 'service__nome')
    
@admin.register(Bloqueio)
class BloqueioAdmin(admin.ModelAdmin):
    list_display = ('barber', 'data_inicio', 'data_fim', 'motivo')
    list_filter = ('barber',)
    search_fields = ('barber__nome_exibicao', 'motivo')
    # Facilita a seleção do barbeiro
    autocomplete_fields = ('barber',)