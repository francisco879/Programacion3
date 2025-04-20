from fastapi import FastAPI, HTTPException, Body, Query, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

from models import Base, Vuelo, EstadoVuelo, ListaVuelos

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de la base de datos
DATABASE_URL = "sqlite:///./vuelos.db"
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(title="Sistema de Gestión de Vuelos")

# Variables globales
lista_vuelos = None

# Modelos Pydantic para la API
class VueloBase(BaseModel):
    codigo: str
    estado: EstadoVuelo
    hora: datetime
    origen: str
    destino: str

class VueloResponse(VueloBase):
    id: int
    
    class Config:
        orm_mode = True

class OrdenVuelos(BaseModel):
    orden_ids: List[int]

# Dependencia para obtener la sesión de la BD
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Inicialización de la lista de vuelos
@app.on_event("startup")
def startup_db_client():
    global lista_vuelos
    session = SessionLocal()
    lista_vuelos = ListaVuelos(session)
    logger.info("Aplicación iniciada - Lista de vuelos cargada desde la BD")

@app.on_event("shutdown")
def shutdown_db_client():
    if lista_vuelos and lista_vuelos.session:
        lista_vuelos.session.close()
        logger.info("Aplicación cerrada - Sesión de BD cerrada")

# Endpoints según los requisitos
@app.post("/vuelos", response_model=VueloResponse)
def agregar_vuelo(vuelo_data: VueloBase, db: Session = Depends(get_db)):
    """Añade un vuelo al final (normal) o al frente (emergencia)."""
    try:
        logger.info(f"Añadiendo vuelo: {vuelo_data.codigo} - Estado: {vuelo_data.estado}")
        
        nuevo_vuelo = Vuelo(
            codigo=vuelo_data.codigo,
            estado=vuelo_data.estado.value,
            hora=vuelo_data.hora,
            origen=vuelo_data.origen,
            destino=vuelo_data.destino
        )
        
        db.add(nuevo_vuelo)
        db.commit()
        db.refresh(nuevo_vuelo)
        
        # Añadir a la lista enlazada según su prioridad
        if vuelo_data.estado == EstadoVuelo.EMERGENCIA:
            lista_vuelos.insertar_al_frente(nuevo_vuelo)
            logger.info(f"Vuelo de emergencia {nuevo_vuelo.codigo} añadido al frente")
        else:
            lista_vuelos.insertar_al_final(nuevo_vuelo)
            logger.info(f"Vuelo regular {nuevo_vuelo.codigo} añadido al final")
            
        return nuevo_vuelo
    except Exception as e:
        db.rollback()
        logger.error(f"Error al añadir vuelo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al agregar vuelo: {str(e)}")

@app.get("/vuelos/total", response_model=int)
def obtener_total_vuelos():
    """Retorna el número total de vuelos en cola."""
    return lista_vuelos.longitud()

@app.get("/vuelos/proximo", response_model=VueloResponse)
def obtener_proximo_vuelo():
    """Retorna el primer vuelo sin remover."""
    vuelo = lista_vuelos.obtener_primero()
    if not vuelo:
        raise HTTPException(status_code=404, detail="No hay vuelos en la lista")
    return vuelo

@app.get("/vuelos/ultimo", response_model=VueloResponse)
def obtener_ultimo_vuelo():
    """Retorna el último vuelo sin remover."""
    vuelo = lista_vuelos.obtener_ultimo()
    if not vuelo:
        raise HTTPException(status_code=404, detail="No hay vuelos en la lista")
    return vuelo

@app.post("/vuelos/insertar", response_model=VueloResponse)
def insertar_vuelo_en_posicion(vuelo_data: VueloBase, posicion: int = Query(..., ge=0), db: Session = Depends(get_db)):
    """Inserta un vuelo en una posición específica."""
    try:
        if posicion > lista_vuelos.longitud():
            raise HTTPException(status_code=400, detail=f"Posición {posicion} fuera de rango (0-{lista_vuelos.longitud()})")
        
        nuevo_vuelo = Vuelo(
            codigo=vuelo_data.codigo,
            estado=vuelo_data.estado.value,
            hora=vuelo_data.hora,
            origen=vuelo_data.origen,
            destino=vuelo_data.destino
        )
        
        db.add(nuevo_vuelo)
        db.commit()
        db.refresh(nuevo_vuelo)
        
        lista_vuelos.insertar_en_posicion(nuevo_vuelo, posicion)
        logger.info(f"Vuelo {nuevo_vuelo.codigo} insertado en posición {posicion}")
        return nuevo_vuelo
    except Exception as e:
        db.rollback()
        logger.error(f"Error al insertar vuelo en posición: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al insertar vuelo: {str(e)}")

@app.delete("/vuelos/extraer", response_model=VueloResponse)
def extraer_vuelo_de_posicion(posicion: int = Query(..., ge=0)):
    """Remueve un vuelo de una posición dada."""
    try:
        if posicion >= lista_vuelos.longitud():
            raise HTTPException(status_code=400, detail=f"Posición {posicion} fuera de rango (0-{lista_vuelos.longitud()-1})")
        
        vuelo = lista_vuelos.extraer_de_posicion(posicion)
        logger.info(f"Vuelo {vuelo.codigo} extraído de posición {posicion}")
        return vuelo
    except Exception as e:
        logger.error(f"Error al extraer vuelo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al extraer vuelo: {str(e)}")

@app.get("/vuelos/lista", response_model=List[VueloResponse])
def listar_todos_los_vuelos():
    """Lista todos los vuelos en orden actual."""
    return lista_vuelos.listar_todos()

@app.patch("/vuelos/reordenar", response_model=List[VueloResponse])
def reordenar_vuelos(orden: OrdenVuelos):
    """Reordena manualmente la cola (por ejemplo, por retrasos)."""
    try:
        return lista_vuelos.reordenar(orden.orden_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al reordenar vuelos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al reordenar vuelos: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


#http://127.0.0.1:8000/docs