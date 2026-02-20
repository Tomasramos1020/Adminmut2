"""
Parche AFIP RG 5616 — Agrega CondicionIVAReceptorId a FECAEDetRequest
Compatible con django-afip 7.1.2
"""

import json
from datetime import date, datetime
from decimal import Decimal

from django_afip import serializers
from creditos.models import Factura

try:
    from zeep.helpers import serialize_object as zeep_serialize_object
except Exception:
    zeep_serialize_object = None

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
LAST_AFIP_PAYLOAD_BY_RECEIPT = {}


def _plain_value(value, depth=0):
    if depth > 8:
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain_value(v, depth + 1) for v in value]
    if hasattr(value, "__dict__"):
        data = {}
        for key, val in vars(value).items():
            if key.startswith("_") or callable(val):
                continue
            data[key] = _plain_value(val, depth + 1)
        if data:
            return data
    return str(value)


def _serialize_payload(serialized):
    if zeep_serialize_object is not None:
        try:
            return _plain_value(zeep_serialize_object(serialized))
        except Exception:
            pass
    return _plain_value(serialized)


def get_last_payload_for_receipt(receipt):
    receipt_id = getattr(receipt, "id", None)
    if receipt_id is None:
        return None
    return LAST_AFIP_PAYLOAD_BY_RECEIPT.get(receipt_id)


def get_last_payload_json_for_receipt(receipt):
    payload = get_last_payload_for_receipt(receipt)
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)


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

        receipt_id = getattr(receipt, "id", None)
        if receipt_id is not None:
            LAST_AFIP_PAYLOAD_BY_RECEIPT[receipt_id] = _serialize_payload(serialized)

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




