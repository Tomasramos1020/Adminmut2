from django.urls import path
from .views import *

urlpatterns = [
	path('', res_index, name='resumenes'),
	path('<str:resumen>/', res_par, name='res_par'),
	path('g/saldos-pendientes/', res_sp, name='saldos-pendientes-de-socios'),
	path('g/cobranzas/', res_cob, name='cobranzas-y-medios'),
	path('g/deudas-pendientes/', res_dp, name='deudas-pendientes-con-acreedores'),
	path('g/pagos/', res_pagos, name='pagos-y-medios'),
	path('g/estado-de-cuenta/', res_edc, name='estado-de-cuenta'),
	path('g/estado-de-cuenta-proveedores/', res_edcp, name='estado-de-cuenta-proveedores'),
	path('g/movimientos-de-caja/', res_mdc, name='movimientos-de-caja'),
	path('g/ingresos-devengados/', res_id, name='ingresos-devengados'),
	path('g/gastos-devengados/', res_gd, name='gastos-devengados'),
	path('g/estado-de-deuda/', res_edd, name='estado-de-deuda'),
	path('g/costo-mercaderia-vendida/', res_cmv, name='costo-de-mercaderia-vendida'),
	path('g/valorizacion-stock/', res_val_stock, name='valorizacion-de-stock-a-fecha'),	
	path("g/resumen-de-solicitudes/", res_sol, name="resumen-de-solicitudes"),
]
