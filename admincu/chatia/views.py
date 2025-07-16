from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.shortcuts import render
from consorcios.models import Consorcio
import requests
import json

def chat_home(request):
    return render(request, 'chat.html')

@csrf_exempt
def chat_ajax(request):    
    if request.method == "POST":
        nombre_usuario = request.user.first_name
        mail = request.user.email
        consorcio = Consorcio.objects.get(usuarios=request.user)
        nombre_mutual = consorcio.nombre
        cuit = consorcio.cuit()
        matricula = consorcio.matricula
        domicilio = consorcio.domicilio
        mensaje = request.POST.get("mensaje")
        if not mensaje:
            return JsonResponse({"error": "Mensaje vacío"}, status=400)

        url = "http://143.198.70.92/agent_response"
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": "3c32b25552ac105e0740aa6ea9b3908d72be1afe78929fdabbe67fba131ebe2b"
        }
        payload = {
            "sender": f"{nombre_usuario}, {mail}, {nombre_mutual}, {cuit}, {matricula}, {domicilio}",
            "message": mensaje
        }
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            data = response.json()

            respuesta = data.get("response", "No se recibió respuesta")

            return JsonResponse({"respuesta": respuesta})
        except Exception as e:
            print("💥 Error llamando al endpoint externo:", e)
            return JsonResponse({"error": "Error al comunicarse con el modelo externo"}, status=500)

    return JsonResponse({"error": "Método no permitido"}, status=405)



# Create your views here.




# Create your views here.
