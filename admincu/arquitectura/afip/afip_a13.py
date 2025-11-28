from django_afip.models import TaxPayer
from pathlib import Path
import subprocess, base64, datetime, requests, html
import xml.etree.ElementTree as ET
from consorcios.models import Consorcio

WSAA_URL = "https://wsaa.afip.gov.ar/ws/services/LoginCms"
PADRON_URL = "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA13"
SERVICE = "ws_sr_padron_a13"
OPENSSL_BIN = "/usr/bin/openssl"


def obtener_taxpayer(cons):
    cuit = int(cons.cuit().replace("-", ""))

    tp = TaxPayer.objects.filter(cuit=cuit).first()
    if not tp:
        raise Exception(f"No existe TaxPayer con CUIT {cuit}")

    key = Path(tp.key.path)
    cert = Path(tp.certificate.path)

    if not key.exists():
        raise Exception(f"Clave privada no encontrada en {key}")
    if not cert.exists():
        raise Exception(f"Certificado no encontrado en {cert}")

    return tp, cert, key


def crear_TRA(service):
    now = datetime.datetime.now()
    gen = (now - datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
    exp = (now + datetime.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
  <header>
    <uniqueId>{int(now.timestamp())}</uniqueId>
    <generationTime>{gen}</generationTime>
    <expirationTime>{exp}</expirationTime>
  </header>
  <service>{service}</service>
</loginTicketRequest>"""

    p = Path("/tmp/TRA.xml")
    p.write_text(xml, encoding="utf-8")
    return p


def firmar_TRA(tra_path, cert_path, key_path):
    cms_path = Path("/tmp/TRA.cms")

    cmd = [
        OPENSSL_BIN, "smime",
        "-sign",
        "-signer", str(cert_path),
        "-inkey", str(key_path),
        "-outform", "DER",
        "-nodetach",
        "-in", str(tra_path),
        "-out", str(cms_path),
    ]

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise Exception("Error firmando TRA:\n" + r.stderr.decode())

    return base64.b64encode(cms_path.read_bytes()).decode()


def obtener_token_sign(login_cms_b64):
    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">
  <SOAP-ENV:Header/>
  <SOAP-ENV:Body>
    <wsaa:loginCms>
      <wsaa:in0>{login_cms_b64}</wsaa:in0>
    </wsaa:loginCms>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""

    resp = requests.post(
        WSAA_URL,
        data=soap.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "loginCms",
        }
    )

    root = ET.fromstring(resp.text)

    fault = root.find(".//{*}faultstring")
    if fault is not None:
        raise Exception(f"WSAA Error: {fault.text}")

    inner = root.find(".//{*}loginCmsReturn")
    if inner is None:
        raise Exception("WSAA no devolvió loginCmsReturn. Ver respuesta arriba.")

    xml2 = html.unescape(inner.text)
    root2 = ET.fromstring(xml2)

    token = root2.find(".//{*}token").text
    sign = root2.find(".//{*}sign").text

    return token, sign



def consultar_padron(request, cuit_consulta):
    cons = Consorcio.objects.get(usuarios=request.user)
    tp, cert_path, key_path = obtener_taxpayer(cons)

    tra = crear_TRA(SERVICE)
    cms = firmar_TRA(tra, cert_path, key_path)
    token, sign = obtener_token_sign(cms)

    soap = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ser="http://a13.soap.ws.server.puc.sr/">
   <soapenv:Header/>
   <soapenv:Body>
      <ser:getPersona>
         <token>{token}</token>
         <sign>{sign}</sign>
         <cuitRepresentada>{tp.cuit}</cuitRepresentada>
         <idPersona>{cuit_consulta}</idPersona>
      </ser:getPersona>
   </soapenv:Body>
</soapenv:Envelope>"""

    resp = requests.post(PADRON_URL, data=soap.encode(), headers={"Content-Type": "text/xml"})
    return resp.text


