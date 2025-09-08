# documentacion/models.py
from django.db import models
from arquitectura.models import Consorcio, Socio
from django.core.validators import MaxLengthValidator

class DocumentoBase(models.Model):
    consorcio   = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre      = models.CharField(max_length=200)
    fecha       = models.DateField(null=True, blank=True)
    numero      = models.IntegerField(null=True, blank=True)  # sólo lo usaremos donde aplique
    contenido   = models.TextField(blank=True, null=True)  # <<— EL CUERPO DEL DOCUMENTO (texto)
    descripcion = models.TextField(blank=True, null=True)  # opcional para notas
    firma = models.BooleanField(default=False)
    transcripcion = models.BooleanField(default=False)

    class Meta:
        abstract = True
        ordering = ["-fecha", "nombre"]

    def __str__(self):
        return self.nombre or f"{self.__class__.__name__} #{self.pk}"

# — Tipos concretos —
class Estatuto(DocumentoBase):
        # Estatuto: textos MUY largos (p.ej. 50 páginas)
    contenido = models.TextField(
        blank=True, null=True,
        validators=[MaxLengthValidator(2_000_000)]  # ej. ~2MB en caracteres
    )
    # Estatuto: no lleva integrantes. Podés usar/ignorar 'numero' según tu preferencia.

class ActaConsejo(DocumentoBase):
    # Actas: suelen ser más cortas
    contenido = models.TextField(
        blank=True, null=True,
        validators=[MaxLengthValidator(50_000)]  # ~50k chars (~15–25 pág. texto plano)
    )
    integrantes = models.ManyToManyField(Socio, blank=True)
    foja = models.IntegerField(null=True, blank=True)

    class Meta(DocumentoBase.Meta):
        verbose_name = "Acta de Consejo"
        verbose_name_plural = "Actas de Consejo"

class ActaJuntaFiscalizadora(DocumentoBase):
    contenido = models.TextField(
        blank=True, null=True,
        validators=[MaxLengthValidator(50_000)]
    )
    integrantes = models.ManyToManyField(Socio, blank=True)
    foja = models.IntegerField(null=True, blank=True)

    class Meta(DocumentoBase.Meta):
        verbose_name = "Acta de Junta Fiscalizadora"
        verbose_name_plural = "Actas de Junta Fiscalizadora"

class ActaAsamblea(DocumentoBase):
    contenido = models.TextField(
        blank=True, null=True,
        validators=[MaxLengthValidator(50_000)]
    )
    integrantes = models.ManyToManyField(Socio, blank=True)
    foja = models.IntegerField(null=True, blank=True)

    class Meta(DocumentoBase.Meta):
        verbose_name = "Acta de Asamblea"
        verbose_name_plural = "Actas de Asamblea"

class ConvenioDoc(DocumentoBase):
    # Podés fijar otro umbral si tus convenios son medianos
    contenido = models.TextField(
        blank=True, null=True,
        validators=[MaxLengthValidator(200_000)]
    )


# Create your models here.
