from django.urls import path
from . import views
from django.views.generic import TemplateView

# Damos um 'nome' para o nosso app para evitar conflitos
app_name = 'core'

urlpatterns = [
    path('', views.HomePageView.as_view(), name='homepage'),
    
    path(
        'agendamento/sucesso/<int:pk>/', 
        views.SuccessPageView.as_view(), 
        name='success_page'
    ),
    
    path('painel/', views.PainelView.as_view(), name='painel'),
    
    path(
        'painel/horario/delete/<int:pk>/', 
        views.DeleteAvailabilityView.as_view(), 
        name='delete_availability'
    ),
    
    path(
        'api/get-available-slots/', 
        views.GetAvailableSlotsView.as_view(), 
        name='get_available_slots'
    ),
    
    path(
        'api/create-appointment/', 
        views.CreateAppointmentView.as_view(), 
        name='create_appointment'
    ),
    
    path(
        'painel/appointment/confirm/<int:pk>/', 
        views.ConfirmAppointmentView.as_view(), 
        name='confirm_appointment'
    ),
    
    # URL para cancelar um agendamento (ex: /painel/appointment/cancel/10/)
    path(
        'painel/appointment/cancel/<int:pk>/', 
        views.CancelAppointmentView.as_view(), 
        name='cancel_appointment'
    ),
]