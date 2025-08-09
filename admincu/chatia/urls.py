from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_home, name='chatia'),
    path('ajax/', views.chat_ajax, name='chat_ajax'),
    path('history/', views.chat_history, name='chat_history'),  # NUEVO
]