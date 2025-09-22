from django.db import models
from arquitectura.models import Cultivo, Establecimiento, Socio, Campaña, ZonasPorCultivo
from consorcios.models import Consorcio
from decimal import Decimal

# Create your models here.


class Solicitud(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	socio = models.ForeignKey(Socio, on_delete=models.CASCADE)
	fecha = models.DateField()
	campaña = models.ForeignKey(Campaña, null=True, blank=True, on_delete=models.CASCADE)
	suscripcion = models.DecimalField("Suscripcion", max_digits=10, decimal_places=2, default=Decimal('0.00'))

class SolicitudLinea(models.Model):
	solicitud = models.ForeignKey(Solicitud, on_delete=models.CASCADE, related_name='lineas')
	establecimiento = models.ForeignKey(Establecimiento, on_delete=models.CASCADE)
	participacion = models.DecimalField("Participacion", max_digits=10, decimal_places=2, default=Decimal('0.00'))
	hectarea = models.DecimalField("Hectareas", max_digits=10, decimal_places=2, default=Decimal('0.00'))
	cultivo = models.ForeignKey(Cultivo, null=True, blank=True, on_delete=models.CASCADE)
	subsidio_max = models.DecimalField("Subsidio max QQ", max_digits=10, decimal_places=2, default=Decimal('0.00'))
	aporte_max = models.DecimalField("% Aporte max", max_digits=10, decimal_places=2, default=Decimal('0.00'))
	aporte_total_qq = models.DecimalField("Aporte total QQ", max_digits=10, decimal_places=2, default=Decimal('0.00'))
	franquicia = models.DecimalField("Franquicia", max_digits=10, decimal_places=2, default=Decimal('0.00'))

	@property
	def franquicia_calc(self):
		"""
		Devuelve la franquicia (%) según ZonasPorCultivo para
		(zona del establecimiento, cultivo) y el consorcio de la solicitud.
		No persiste nada. Si falta algún dato, devuelve 0.00.
		"""
		try:
			est = self.establecimiento
			zona_id = getattr(est, "zona_id", None)
			cultivo_id = getattr(self, "cultivo_id", None)
			cons_id = getattr(self.solicitud, "consorcio_id", None)

			if not (zona_id and cultivo_id and cons_id):
				return Decimal("0.00")

			val = (ZonasPorCultivo.objects
				   .filter(consorcio_id=cons_id, zona_id=zona_id, cultivo_id=cultivo_id)
				   .values_list("franquicia", flat=True)
				   .first())
			return (Decimal(val).quantize(Decimal("0.01"))
					if val is not None else Decimal("0.00"))
		except Exception:
			# Ante cualquier inconsistencia, devolvemos 0.00 para no romper el PDF
			return Decimal("0.00")
