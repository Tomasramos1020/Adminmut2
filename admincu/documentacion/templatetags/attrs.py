from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name="attrs")
def attrs(obj, attr_name):
    """
    Devuelve obj.<attr_name>. Si es callable, lo llama sin argumentos.
    Si no existe, devuelve None para que funcione con |default_if_none:"".
    """
    if not obj or not attr_name:
        return None
    val = getattr(obj, attr_name, None)
    try:
        return val() if callable(val) else val
    except Exception:
        # Si fallara por ser método con args, devolvemos la repr segura
        return mark_safe(str(val) if val is not None else "")

@register.filter
def key(d, k):
    """Devuelve d[k] o '' si no existe."""
    try:
        return d.get(k, "")
    except Exception:
        return ""