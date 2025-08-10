# chatia/views.py
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render
from consorcios.models import Consorcio
from django.conf import settings
import requests
import json

# Defaults desde settings
DEFAULT_BASE = getattr(settings, "CHATIA_API_URL", "http://localhost:8000")
DEFAULT_KEY  = getattr(settings, "CHATIA_API_KEY", "")
ALT_BASE     = getattr(settings, "CHATIA2_API_URL", "")
ALT_KEY      = getattr(settings, "CHATIA2_API_KEY", "")

def _select_backend(request):
    """
    Elige el backend según la sesión (seteada en chat_home).
    Si no hay nada en sesión, usa los defaults.
    """
    base = request.session.get("agent_base_url") or DEFAULT_BASE
    key  = request.session.get("agent_api_key") or DEFAULT_KEY
    return base, key

def _agent_headers(api_key):
    return {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
    }

def chat_home(request):
    """
    Si viene ?backend=alt usamos el servidor alternativo.
    En caso contrario, usamos el backend por defecto.
    """
    backend = request.GET.get("backend")
    if backend == "alt" and ALT_BASE and ALT_KEY:
        request.session["agent_base_url"] = ALT_BASE
        request.session["agent_api_key"]  = ALT_KEY
    else:
        # Dejá explícito el default para esta ventana
        request.session["agent_base_url"] = DEFAULT_BASE
        request.session["agent_api_key"]  = DEFAULT_KEY

    return render(request, 'chat.html')

def chat_history(request):
    """Proxy interno que trae el historial del usuario autenticado y lo normaliza para el front."""
    if not request.user.is_authenticated:
        return HttpResponseForbidden("No autenticado")

    base_url, api_key = _select_backend(request)
    sender_id = str(request.user.id)
    url = f"{base_url}/history/{sender_id}"

    try:
        r = requests.get(url, headers=_agent_headers(api_key), timeout=15)
        r.raise_for_status()
        data = r.json()
        turns = data.get("history", []) if isinstance(data, dict) else []

        normalized = []
        for t in turns:
            if isinstance(t, dict):
                if t.get("user"):
                    normalized.append({"from": "user", "text": t["user"]})
                if t.get("agent"):
                    normalized.append({"from": "agent", "text": t["agent"]})
        return JsonResponse({"history": normalized})
    except Exception as e:
        print("💥 Error trayendo historial:", e)
        return JsonResponse({"history": []}, status=200)

@csrf_exempt
def chat_ajax(request):
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    base_url, api_key = _select_backend(request)

    user_id = request.user.id
    nombre_usuario = request.user.first_name
    mail = request.user.email

    consorcio = Consorcio.objects.get(usuarios=request.user)
    nombre_mutual = consorcio.nombre
    cuit = consorcio.cuit()
    matricula = consorcio.matricula
    domicilio = consorcio.domicilio
    provincia = consorcio.provincia.nombre

    address = f"{domicilio}, {provincia}"

    mensaje = request.POST.get("mensaje")
    if not mensaje:
        return JsonResponse({"error": "Mensaje vacío"}, status=400)

    url = f"{base_url}/agent_response"
    payload = {
        "sender_id": str(user_id),
        "user_name": nombre_usuario,
        "email": mail,
        "mutual_name": nombre_mutual,
        "cuit": cuit,
        "address": address,
        "registration_number": matricula,
        "message": mensaje,
    }

    try:
        response = requests.post(url, headers=_agent_headers(api_key), data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        data = response.json()
        respuesta = data.get("response", "No se recibió respuesta")
        return JsonResponse({"respuesta": respuesta})
    except Exception as e:
        print("💥 Error llamando al endpoint externo:", e)
        return JsonResponse({"error": "Error al comunicarse con el modelo externo"}, status=500)
