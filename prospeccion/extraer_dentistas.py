"""Extrae consultorios dentales (SCIAN 62121x) del DENUE del INEGI por zona metropolitana.
Uso: python extraer_dentistas.py denue_00_62_csv.zip salida.csv"""
import csv, io, sys, zipfile

ZM = {
"Valle de México (CDMX y área metropolitana)": ["09*","15002","15009","15010","15011","15013","15015","15016","15017","15020","15022","15023","15024","15025","15028","15029","15030","15031","15033","15034","15035","15036","15037","15038","15039","15044","15046","15050","15053","15057","15058","15059","15060","15061","15065","15068","15069","15070","15075","15081","15083","15084","15089","15091","15092","15093","15094","15095","15096","15099","15100","15103","15104","15108","15109","15112","15120","15121","15122","15125","13069"],
"Guadalajara": ["14039","14120","14098","14101","14097","14070","14044","14051","14124","14002"],
"Monterrey": ["19039","19026","19046","19006","19021","19048","19019","19018","19031","19010","19009","19025","19041","19045","19049","19012","19001"],
"Puebla": ["21114","21119","21140","21041","21015","21034","21090","21074","21132","21125","21136","21106"],
"Tijuana": ["02004","02005","02003"],
"León": ["11020","11037"],
"Querétaro": ["22014","22011","22006","22008"],
"Toluca": ["15106","15054","15118","15051","15076","15005","15062","15115","15018","15067","15090","15072","15087","15027","15055","15073"],
"Mérida": ["31050","31041","31100","31059","31013","31102"],
"Morelia": ["16053","16022","16088"],
"San Luis Potosí": ["24028","24035"],
"Aguascalientes": ["01001","01005","01011"],
"Mexicali": ["02002"],
"Juárez (Chihuahua)": ["08037"],
"Chihuahua": ["08019","08004","08002"],
"Culiacán": ["25006"],
"Saltillo": ["05030","05027","05004"],
"La Laguna (Torreón-Gómez Palacio)": ["05035","05017","10007","10012"],
"Hermosillo": ["26030"],
"Xalapa": ["30087","30026","30038","30065","30182","30093"],
"Oaxaca": ["20067","20390","20385","20157","20399","20107"],
"Cancún": ["23005"],
"Tuxtla Gutiérrez": ["07101","07027","07012"],
"Cuernavaca": ["17007","17011","17020","17028","17018","17024"],
"Pachuca": ["13048","13051","13052"],
"Durango": ["10005"],
"Tepic": ["18017","18008"],
"Veracruz": ["30193","30028","30011"],
"Villahermosa": ["27004","27013"],
"Mazatlán": ["25012"],
}
MAPA = {c: z for z, l in ZM.items() for c in l}
CAMPOS = ["zona_metropolitana","nom_estab","raz_social","codigo_act","per_ocu","tipo_vial","nom_vial","numero_ext",
          "numero_int","tipo_asent","nomb_asent","cod_postal","entidad","municipio","telefono","correoelec","www",
          "latitud","longitud","fecha_alta"]

zf = zipfile.ZipFile(sys.argv[1])
nombre = next(n for n in zf.namelist() if n.startswith("conjunto_de_datos/") and n.endswith(".csv"))
crudo = zf.read(nombre)
try:
    texto = crudo.decode("utf-8")
except UnicodeDecodeError:
    texto = crudo.decode("latin-1")
lector = csv.DictReader(io.StringIO(texto))
with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, CAMPOS)
    w.writeheader()
    n = 0
    for r in lector:
        if not (r.get("codigo_act") or "").startswith("62121"):
            continue
        clave = r["cve_ent"] + r["cve_mun"]
        z = MAPA.get(clave) or MAPA.get(r["cve_ent"] + "*")
        r["zona_metropolitana"] = z or ""
        w.writerow({k: r.get(k, "") for k in CAMPOS})
        n += 1
print("consultorios dentales:", n)
