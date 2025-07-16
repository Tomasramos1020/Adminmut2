from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_home, name='chatia'),
    path('ajax/', views.chat_ajax, name='chat_ajax'),
]