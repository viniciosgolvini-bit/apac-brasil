from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from geopy.geocoders import Nominatim
import httpx
import uvicorn
import os

app = FastAPI()

# LIBERAÇÃO DE SEGURANÇA (Essencial para funcionar na internet)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GPS configurado para o Brasil com tempo de resposta maior (Timeout)
geolocator = Nominatim(user_agent="apac_brasil_v10", timeout=30)

class DadosRota(BaseModel):
    origem: str
    destino: str
    consumo_kml: float
    peso_kg: float = 35000

@app.post("/calcular-real")
async def calcular_real(dados: DadosRota):
    try:
        # 1. Localização em qualquer lugar do Brasil
        loc_o = geolocator.geocode(dados.origem, country_codes="br")
        loc_d = geolocator.geocode(dados.destino, country_codes="br")
        
        if not loc_o or not loc_d:
            raise HTTPException(status_code=400, detail="Cidade não encontrada no Brasil.")

        # 2. Rota Real via Satélite (OSRM)
        url = f"http://router.project-osrm.org/route/v1/driving/{loc_o.longitude},{loc_o.latitude};{loc_d.longitude},{loc_d.latitude}?overview=full&geometries=geojson"
        
        async with httpx.AsyncClient(timeout=40.0) as client:
            res = await client.get(url)
            route = res.json()

        if 'routes' not in route or len(route['routes']) == 0:
            raise HTTPException(status_code=500, detail="Não foi possível traçar a rota entre esses pontos.")

        dist_km = route['routes'][0]['distance'] / 1000
        tempo_min = route['routes'][0]['duration'] / 60
        
        # 3. Inteligência de Diagnóstico APAC (Nacional)
        fator_vicio = 0.38 if dist_km < 150 else 0.18 # Mais desperdício em rotas curtas/urbanas
        
        ideal_L = dist_km / dados.consumo_kml
        perda_L = (tempo_min / 60) * 8.5 * fator_vicio # 8.5L/h é a média de desperdício em marcha lenta/baixa
        total_L = ideal_L + perda_L
        
        # Mapa Estático Dinâmico (Fallback para o Leaflet no HTML)
        mapa_link = f"https://static-maps.yandex.ru/1.x/?lang=pt_BR&ll={(loc_o.longitude+loc_d.longitude)/2},{(loc_o.latitude+loc_d.latitude)/2}&z=6&l=map&pt={loc_o.longitude},{loc_o.latitude},pm2gnm~{loc_d.longitude},{loc_d.latitude},pm2rdm"

        return {
            "distancia": round(dist_km, 1),
            "resultado": {
                "ideal_L": round(ideal_L, 2),
                "total_L": round(total_L, 2),
                "economia_perc": f"{round((perda_L/total_L)*100, 1)}%"
            },
            "reajuste": {
                "economia_L": round(perda_L * 0.75, 2) # 75% da perda é recuperável com a reengenharia
            },
            "diagnostico_infra": {
                "local_vilao": "Gargalo por Inércia Interrompida" if dist_km < 100 else "Gargalo de Malha Rodoviária Nacional",
                "rota_desvio": "Priorizar vias expressas e otimizar janelas de aceleração constante.",
                "impacto_desvio": "Redução de até 12% no custo direto",
                "mapa_url": mapa_link,
                "lat_o": loc_o.latitude, "lon_o": loc_o.longitude,
                "lat_d": loc_d.latitude, "lon_d": loc_d.longitude
            }
        }
    except Exception as e:
        print(f"Erro: {e}")
        raise HTTPException(status_code=500, detail="O servidor de mapas falhou. Tente novamente.")

if __name__ == "__main__":
    # Configuração para rodar local ou na Nuvem (Render/Railway)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)