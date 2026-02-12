"""
Parche AFIP RG 5616 — Agrega CondicionIVAReceptorId a FECAEDetRequest
Compatible con django-afip 7.1.2
"""

from django_afip import serializers
from creditos.models import Factura

CODIGO_AFIP = {
    "1": 1,  # Responsable Inscripto
    "2": 2,  # Responsable no Inscripto
    "3": 3,  # No Responsable
    "4": 4,  # Exento
    "5": 5,  # Consumidor Final
    "6": 6,  # Monotributo
    "7": 7,  # Sujeto No Categorizado
}

_original_serialize_receipt = serializers.serialize_receipt


def serialize_receipt_with_cond_iva(receipt):
    serialized = _original_serialize_receipt(receipt)

    try:
        factura = Factura.objects.filter(receipt=receipt).select_related(
            "socio__condicionIVA"
        ).first()

        socio = factura.socio if factura else None
        condicion = socio.condicionIVA if socio else None

        # Si no hay condición IVA, se usa Consumidor Final (5)
        codigo = condicion.codigo if condicion else "5"
        codigo_afip = CODIGO_AFIP.get(codigo, 5)

        # EL CAMPO CORRECTO:
        serialized.CondicionIVAReceptorId = codigo_afip

        if condicion:
            print(
                f"[CONDIVA] agregado → socio={socio.id} "
                f"codigo={codigo} afip={codigo_afip}"
            )
        else:
            print("[CONDIVA] sin condición IVA → usando CF (5)")

    except Exception as e:
        print("[CONDIVA] ERROR:", e)

    return serialized


serializers.serialize_receipt = serialize_receipt_with_cond_iva

print("[AFIP-PATCH] Patch CondicionIVAReceptorId activo.")





