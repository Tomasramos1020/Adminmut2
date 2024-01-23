from xml.parsers.expat import model
from django.db import models
from arquitectura.models import Consorcio



class Sucursal(models.Model):
    consorcio = models.ForeignKey(Consorcio, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=30)

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

class Comp_Venta(models.Model):
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


# Create your models here.
