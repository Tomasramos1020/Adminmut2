from django import template
from django.contrib.auth.models import Group
from decimal import Decimal, ROUND_DOWN
from num2words import num2words


register = template.Library()
@register.filter(name='add_attr')
def add_attr(field, css):
	attrs = {}
	definition = css.split(',')

	for d in definition:
		if ':' not in d:
			attrs['class'] = d
		else:
			key, val = d.split(':')
			attrs[key] = val

	return field.as_widget(attrs=attrs)


@register.filter(name='multiply')
def multiply(value, arg):
	value = round(float(value)*float(arg),2)
	return Decimal("%.2f" % value)

@register.filter(name='replace_underscores')
def replace_underscores(value):
    return value.replace('_', ' ').title()	


def _masculinizar_un(txt: str) -> str:
    """
    Ajusta 'UNO' -> 'UN' en contextos masculinos y corrige 'VEINTIUNO' -> 'VEINTIÚN'.
    (Suficiente para 'centavo/s')
    """
    txt = txt.replace(" VEINTIUNO", " VEINTIÚN")
    txt = txt.replace(" TREINTA Y UNO", " TREINTA Y UN")
    txt = txt.replace(" CUARENTA Y UNO", " CUARENTA Y UN")
    txt = txt.replace(" CINCUENTA Y UNO", " CINCUENTA Y UN")
    txt = txt.replace(" SESENTA Y UNO", " SESENTA Y UN")
    txt = txt.replace(" SETENTA Y UNO", " SETENTA Y UN")
    txt = txt.replace(" OCHENTA Y UNO", " OCHENTA Y UN")
    txt = txt.replace(" NOVENTA Y UNO", " NOVENTA Y UN")
    # caso general al final
    txt = txt.replace(" UNO", " UN")
    return txt

@register.filter(name='num_to_words')
def num_to_words(value):
    """
    20484360.50 -> 'VEINTE MILLONES ... TRESCIENTOS SESENTA CON CINCUENTA CENTAVOS'
    """
    try:
        valor = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        entero = int(valor)
        centavos = int((valor - entero) * 100)

        letras_entero = num2words(entero, lang='es').upper()
        letras_cent = num2words(centavos, lang='es').upper()
        letras_cent = _masculinizar_un(letras_cent)
        sufijo_cent = "CENTAVO" if centavos == 1 else "CENTAVOS"

        return f"{letras_entero} CON {letras_cent} {sufijo_cent}"
    except Exception:
        return ""
