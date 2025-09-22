from django.contrib import admin
from .models import *

class SucursalAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class Proveedor_proveeduriaAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class RubroAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class ProductoAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class DepositoAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class StockAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class TransporteAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']
    
class Notas_PedidoAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class Consol_CargaAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class Guia_DistriAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']

class InformeAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio'] 

class Recibo_ProveeAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']  

class VendendorAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']  
      
class Comp_VentaAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']    

class Venta_ProductoAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']
class Compra_ProductoAdmin(admin.ModelAdmin):
	list_display = ['__str__', 'consorcio']
	list_filter = ['consorcio']	    
class MovimientoStockAdmin(admin.ModelAdmin):
	list_display = ['__str__']
# admin.py (opcional)
@admin.register(Remito)
class RemitoAdmin(admin.ModelAdmin):
    list_display = ('id','numero','consorcio','fecha','deposito','socio')
    search_fields = ('numero',)
    list_filter = ('consorcio','deposito','fecha')

@admin.register(RemitoItem)
class RemitoItemAdmin(admin.ModelAdmin):
    list_display = ('remito','producto','cantidad')
    search_fields = ('remito__numero','producto__nombre')



admin.site.register(Sucursal, SucursalAdmin)
admin.site.register(Proveedor_proveeduria, Proveedor_proveeduriaAdmin)
admin.site.register(Rubro, RubroAdmin)
admin.site.register(Producto, ProductoAdmin)
admin.site.register(Deposito, DepositoAdmin)
admin.site.register(Stock, StockAdmin)
admin.site.register(Transporte, TransporteAdmin)
admin.site.register(Notas_Pedido, Notas_PedidoAdmin)
admin.site.register(Consol_Carga, Consol_CargaAdmin)
admin.site.register(Guia_Distri, Guia_DistriAdmin)
admin.site.register(Informe, InformeAdmin)
admin.site.register(Recibo_Provee, Recibo_ProveeAdmin)
admin.site.register(Vendendor, VendendorAdmin)
admin.site.register(Comp_Venta, Comp_VentaAdmin)
admin.site.register(Venta_Producto, Venta_ProductoAdmin)
admin.site.register(Compra_Producto, Compra_ProductoAdmin)
admin.site.register(MovimientoStock, MovimientoStockAdmin)





# Register your models here.

