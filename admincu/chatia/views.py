# chatia/views.py
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render
from consorcios.models import Consorcio
import requests
import json
from django.conf import settings


AGENT_BASE_URL = getattr(settings, "CHATIA_API_URL")
AGENT_API_KEY  = getattr(settings, "CHATIA_API_KEY")

def chat_home(request):
    return render(request, 'chat.html')

def _agent_headers():
    return {
        "Content-Type": "application/json",
        "X-API-KEY": AGENT_API_KEY,
    }

def chat_history(request):
    """Proxy interno que trae el historial del usuario autenticado y lo normaliza para el front."""
    if not request.user.is_authenticated:
        return HttpResponseForbidden("No autenticado")

    sender_id = str(request.user.id)
    url = f"{AGENT_BASE_URL}/history/{sender_id}"

    try:
        r = requests.get(url, headers=_agent_headers(), timeout=15)
        r.raise_for_status()
        data = r.json()
        # Si el servicio responde "message: No se encontró..." devolvemos lista vacía
        turns = data.get("history", []) if isinstance(data, dict) else []

        # Normalizamos a una lista de mensajes atómicos [{from:'user'|'agent', text:'...'}]
        normalized = []
        for t in turns:
            if "user" in t and t["user"]:
                normalized.append({"from": "user", "text": t["user"]})
            if "agent" in t and t["agent"]:
                normalized.append({"from": "agent", "text": t["agent"]})
        return JsonResponse({"history": normalized})
    except Exception as e:
        print("💥 Error trayendo historial:", e)
        # Fallo silencioso con lista vacía para no romper el chat
        return JsonResponse({"history": []}, status=200)

@csrf_exempt
def chat_ajax(request):
    if request.method == "POST":
        user_id = request.user.id
        nombre_usuario = request.user.first_name
        mail = request.user.email

        consorcio = Consorcio.objects.get(usuarios=request.user)
        nombre_mutual = consorcio.nombre
        cuit = consorcio.cuit()
        matricula = consorcio.matricula
        domicilio = consorcio.domicilio
        provincia = consorcio.provincia.nombre

        # Formato requerido: "domicilio, localidad, provincia"
        # En tu modelo "localidad" viene adentro de domicilio
        address = f"{domicilio}, {provincia}"

        mensaje = request.POST.get("mensaje")
        if not mensaje:
            return JsonResponse({"error": "Mensaje vacío"}, status=400)

        url = f"{AGENT_BASE_URL}/agent_response"
        payload = {
            "sender_id": str(user_id),
            "user_name": nombre_usuario,
            "email": mail,
            "mutual_name": nombre_mutual,
            "cuit": cuit,
            "address": address,
            "registration_number": matricula,
            "message": mensaje
        }
        try:
            response = requests.post(url, headers=_agent_headers(), data=json.dumps(payload), timeout=30)
            response.raise_for_status()
            data = response.json()
            respuesta = data.get("response", "No se recibió respuesta")
            return JsonResponse({"respuesta": respuesta})
        except Exception as e:
            print("💥 Error llamando al endpoint externo:", e)
            return JsonResponse({"error": "Error al comunicarse con el modelo externo"}, status=500)

    return JsonResponse({"error": "Método no permitido"}, status=405)
