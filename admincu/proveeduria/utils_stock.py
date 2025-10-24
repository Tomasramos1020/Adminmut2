# proveeduria/utils_stock.py  (creá este archivo)

from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import MovimientoStock, ModuloComponente, Producto

Q00 = Decimal('0.00')

@transaction.atomic
def mover_stock_por_producto(
    *,
    producto: Producto,
    deposito,
    fecha,
    cantidad_signed: Decimal,
    venta_producto=None,
    remito_item=None,
    ajuste_item=None,
):
    """
    Crea movimientos de stock.
    - Si el producto es módulo: explota a componentes y mueve cada uno por (cantidad_signed * coef).
    - Si NO es módulo: mueve el propio producto por cantidad_signed.
    cantidad_signed > 0  => entrada
    cantidad_signed < 0  => salida
    """

    if cantidad_signed == 0:
        return

    # Módulo -> explotar componentes
    if getattr(producto, 'es_modulo', False):
        comps = list(ModuloComponente.objects.select_related('componente').filter(producto_modulo=producto))
        if not comps:
            raise ValidationError(f"El módulo '{producto}' no tiene componentes definidos.")

        for c in comps:
            cant_comp = (Decimal(c.cantidad or 0) * Decimal(cantidad_signed)).quantize(Decimal('0.01'))
            if cant_comp == 0:
                continue

            MovimientoStock.objects.create(
                producto=c.componente,
                deposito=deposito,
                fecha=fecha,
                cantidad=cant_comp,  # ya con signo
                venta_producto=venta_producto,
                remito_item=remito_item,
                ajuste_item=ajuste_item,
            )
        return

    # Producto normal
    MovimientoStock.objects.create(
        producto=producto,
        deposito=deposito,
        fecha=fecha,
        cantidad=cantidad_signed,
        venta_producto=venta_producto,
        remito_item=remito_item,
        ajuste_item=ajuste_item,
    )
