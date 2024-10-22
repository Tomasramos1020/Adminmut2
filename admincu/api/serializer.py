from rest_framework import serializers

class SocioSerializer(serializers.Serializer):


	SOCIO = serializers.IntegerField(source='id')
	NOMBRE = serializers.SerializerMethodField()	
	CUIT = serializers.IntegerField(source='numero_documento')
	NUMERO_ASOCIADO = serializers.CharField(source='numero_asociado')
	DIRECCION = serializers.CharField(source='domicilio')
	NUMERO_CALLE = serializers.CharField(source='numero_calle')
	PROVINCIA = serializers.CharField(source='provincia')	
	LOCALIDAD = serializers.CharField(source='localidad')	
	CONDICION = serializers.SerializerMethodField()
	CATEGORIA = serializers.CharField(source='tipo_asociado')
	CONVENIO = serializers.CharField(source='convenio')
	EMAIL = serializers.EmailField(source='mail')
	


	def get_NOMBRE(self, obj):
		return obj.__str__()

	def get_CONDICION(self, obj):
		if obj.baja:
			return "BAJA"
		else:
			return "VIGENTE"

	def get_MOROSO(self, obj):
		return 0

	def get_RELACION(self, obj):
		if obj.baja:
			"BAJA"
		else:
			"ACTIVO"