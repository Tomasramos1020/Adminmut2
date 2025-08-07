from xml.parsers.expat import model
from django.db import models
from arquitectura.models import Consorcio, Socio
from creditos.models import Credito, Factura, Liquidacion
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from django.utils.functional import cached_property


class Sucursal(models.Model):
	LISTA_CHOICES = (
			('1', 'Lista de precios 1'),
			('2', 'Lista de precios 2'),
			('3', 'Lista de precios 3'),
			('4', 'Lista de precios 4'),
		)

	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30, blank=True, null=True)
	direccion =  models.CharField(max_length=50, blank=True, null=True)
	localidad = models.CharField(max_length=50, blank=True, null=True)
	provincia = models.CharField(max_length=50, blank=True, null=True)
	mail = models.CharField(max_length=50, blank=True, null=True)
	socio = models.ForeignKey(Socio, on_delete=models.CASCADE, null=True, blank=True)
	lista_precio = models.CharField(max_length=15, choices=LISTA_CHOICES, default='1')
	def __str__(self):
		return self.nombre

class Proveedor_proveeduria(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)
	def __str__(self):
		return self.nombre

class Rubro(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)
	def __str__(self):
		return self.nombre

class Producto(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Deposito(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Stock(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Transporte(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Notas_Pedido(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Consol_Carga(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Guia_Distri(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Informe(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Recibo_Provee(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

class Vendendor(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	nombre = models.CharField(max_length=30)

	def __str__(self):
		return self.nombre

class Comp_Venta(models.Model):
	consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
	sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, blank=True, null=True)
	nombre = models.CharField(max_length=30)
	vendedor = models.ForeignKey(Vendendor, on_delete=models.CASCADE, blank=True, null=True)
	deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE, blank=True, null=True)
	transporte = models.ForeignKey(Transporte, on_delete=models.CASCADE, blank=True, null=True)
	fecha_entrega = models.DateField(blank=True, null=True)
	factura = models.ForeignKey(Factura, on_delete=models.CASCADE, blank=True, null=True)
	liquidacion = models.ForeignKey(Liquidacion, blank=True, null=True, on_delete=models.CASCADE)		


# Create your models here.
