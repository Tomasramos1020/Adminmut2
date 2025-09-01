# signals.py
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Compra_Producto  # ajustá import
from .models import Producto

@receiver(post_save, sender=Compra_Producto)
def actualizar_costo_por_compra(sender, instance, created, **kwargs):
    """
    Cuando se crea (o actualiza) una compra de producto,
    actualizamos el costo del producto con el precio de esa compra.
    Si no querés que sea al actualizar, chequeá `if created:` solamente.
    """
    if not instance or instance.precio is None or instance.producto_id is None:
        return
    # Si querés sólo en creación, descomentá:
    # if not created:
    #     return

    producto = instance.producto
    try:
        nuevo_costo = Decimal(instance.precio)
    except Exception:
        return

    # Podés agregar lógica para decidir si actualizar siempre o sólo si es más reciente, etc.
    producto.costo = nuevo_costo.quantize(Decimal('0.01'))
    producto.save(update_fields=['costo'])
