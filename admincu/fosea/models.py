from django.db import models
from arquitectura.models import Cultivo, Establecimiento, Socio, Campaña, ZonasPorCultivo, Cotizacion
from consorcios.models import Consorcio
from decimal import Decimal, ROUND_HALF_UP
from consorcios.models import Consorcio
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
	
	
	@property
	def hectareas_reales(self):
		hect_reales = Decimal(self.hectarea) * (Decimal(self.participacion) / Decimal("100"))
		return hect_reales.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)



LIBERACION_OPCIONES = (
	('plena', 'Cobertura plena (100%)'),
	('resiembra_etapa', 'Etapa resiembra (40%)'),
	('liberacion_lote', 'Liberación de lote (80%)'),
	('resiembra_efectiva', 'Resiembra efectiva (20%)'),
)

LIBERACION_FACTORES = {
	'plena': Decimal('1.00'),
	'resiembra_etapa': Decimal('0.40'),
	'liberacion_lote': Decimal('0.80'),
	'resiembra_efectiva': Decimal('0.20'),
}


class Siniestro(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	socio = models.ForeignKey(Socio, on_delete=models.CASCADE)
	fecha = models.DateField()
	campaña = models.ForeignKey(Campaña, null=True, blank=True, on_delete=models.SET_NULL)

	# Totales (se mantienen por conveniencia; se recalculan en save())
	indemnizacion_total_qq = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
	indemnizacion_total_ajustada = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

	class Meta:
		ordering = ['-id']

	def __str__(self):
		return f"Siniestro #{self.pk or '—'} - {self.socio}"

	def recomputar_totales(self):
		qs = self.lineas.all()
		total_qq = sum((l.indemnizacion_qq or Decimal('0')) for l in qs) or Decimal('0')
		total_ajustada = sum((l.indemnizacion_ajustada or Decimal('0')) for l in qs) or Decimal('0')

		self.indemnizacion_total_qq = total_qq.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
		self.indemnizacion_total_ajustada = total_ajustada.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


	def save(self, *args, **kwargs):
		super().save(*args, **kwargs)
		# Recalcular totales cada vez (si no querés overhead, se puede mover a una signal post_save en líneas)
		self.recomputar_totales()
		super().save(update_fields=['indemnizacion_total_qq', 'indemnizacion_total_ajustada'])


class SiniestroLinea(models.Model):
	siniestro = models.ForeignKey(Siniestro, on_delete=models.CASCADE, related_name='lineas')
	establecimiento = models.ForeignKey(Establecimiento, on_delete=models.CASCADE)
	cultivo = models.ForeignKey(Cultivo, on_delete=models.CASCADE)

	hectareas_afectadas = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
	danio_porcentaje = models.DecimalField("Daño (%)", max_digits=5, decimal_places=2, default=Decimal('0.00'))

	# Se autocompletan desde ZonasPorCultivo
	franquicia_porcentaje = models.DecimalField("Franquicia (%)", max_digits=5, decimal_places=2,
												default=Decimal('0.00'))
	cobertura_qq = models.DecimalField("Cobertura (QQ/ha)", max_digits=10, decimal_places=2,
									   default=Decimal('0.00'))

	estadio = models.CharField(max_length=32, blank=True, null=True)
	liberacion = models.CharField(max_length=32, choices=LIBERACION_OPCIONES, default='plena')

	# Resultados
	indemnizacion_qq = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
	indemnizacion_ajustada = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

	class Meta:
		ordering = ['id']

	def __str__(self):
		return f"Línea #{self.pk or '—'} ({self.establecimiento})"

	# --- Helpers internos ---
	

	def _resolver_parametros(self):
		"""
		Actualiza franquicia (%) y cobertura (QQ/ha).
		- Franquicia: desde ZonasPorCultivo.
		- Cobertura: máximo subsidio_max registrado en SolicitudLinea
		para el mismo establecimiento/cultivo en la campaña del siniestro.
		"""
		# --- franquicia base ---
		zpc = None
		try:
			zpc = ZonasPorCultivo.objects.get(
				consorcio=self.siniestro.consorcio,
				zona=self.establecimiento.zona,
				cultivo=self.cultivo
			)
		except ZonasPorCultivo.DoesNotExist:
			pass

		if zpc:
			self.franquicia_porcentaje = Decimal(zpc.franquicia or 0).quantize(Decimal("0.01"))
		else:
			self.franquicia_porcentaje = self.franquicia_porcentaje or Decimal("0.00")

		# --- cobertura: buscar el máximo subsidio cargado ---
		from fosea.models import SolicitudLinea  # ajustar si está en otro módulo
		from django.db.models import Max
		try:
			max_subsidio = (
				SolicitudLinea.objects
				.filter(
					solicitud__campaña=self.siniestro.campaña,
					solicitud__socio=self.siniestro.socio,
					solicitud__consorcio=self.siniestro.consorcio,
					establecimiento=self.establecimiento,
					cultivo=self.cultivo
				)
				.aggregate(Max('subsidio_max'))
				.get('subsidio_max__max')
			)
			if max_subsidio is not None:
				self.cobertura_qq = Decimal(max_subsidio).quantize(Decimal('0.01'))
		except Exception:
			pass



	def _cotizacion_cultivo(self):
		"""Última cotización del cultivo para el consorcio del siniestro."""
		try:
			c = Cotizacion.objects.filter(
				consorcio=self.siniestro.consorcio,
				producto=self.cultivo
			).order_by('-fecha').first()
			return Decimal(c.cotizacion)
		except Exception:
			return None

	def recomputar_indemnizacion(self):
		"""
		Calcula indemnización en QQ y su valor ajustado según la campaña.
		Fórmula base:
			indemn_qq = ha * cobertura_qq * max(0, daño% * liberación_factor - franquicia%)
			indemn_ajustada = indemn_qq * (1 - campaña.ajuste / 100)
		"""
		ha = Decimal(self.hectareas_afectadas or 0)
		cobertura = Decimal(self.cobertura_qq or 0)
		danio = (Decimal(self.danio_porcentaje or 0) / Decimal('100'))
		franquicia = (Decimal(self.franquicia_porcentaje or 0) / Decimal('100'))
		liber_factor = LIBERACION_FACTORES.get(self.liberacion, Decimal('1.00'))

		factor = (danio * liber_factor) - franquicia
		if factor < 0:
			factor = Decimal('0')

		indemn_qq = (ha * cobertura * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
		self.indemnizacion_qq = indemn_qq

		# Ajuste según campaña
		ajuste = Decimal('0.00')
		try:
			ajuste = Decimal(self.siniestro.campaña.ajuste or 0)
		except Exception:
			pass

		self.indemnizacion_ajustada = (
			indemn_qq * (Decimal('1.00') - (ajuste / Decimal('100')))
		).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


	def save(self, *args, **kwargs):
		# Asegurar params antes de calcular
		self._resolver_parametros()
		self.recomputar_indemnizacion()
		super().save(*args, **kwargs)
		# Actualiza totales del padre
		self.siniestro.recomputar_totales()
		self.siniestro.save(update_fields=['indemnizacion_total_qq', 'indemnizacion_total_ajustada'])
