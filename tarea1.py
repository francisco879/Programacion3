from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, Enum, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime
import enum

# Configuración de la base de datos
DATABASE_URL = "sqlite:///./rpg6.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Enumeración para el estado de la misión
class EstadoMision(str, enum.Enum):
    pendiente = "pendiente"
    completada = "completada"

# Modelos ORM
class Mision(Base):
    __tablename__ = 'misiones'
    id = Column(Integer, primary_key=True)
    nombre = Column(String(50), nullable=False)
    descripcion = Column(Text)
    experiencia = Column(Integer, default=0)
    estado = Column(Enum(EstadoMision), default=EstadoMision.pendiente)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)

    personajes = relationship("MisionPersonaje", back_populates="mision")

class Personaje(Base):
    __tablename__ = 'personajes'
    id = Column(Integer, primary_key=True)
    nombre = Column(String(30), nullable=False)

    misiones = relationship("MisionPersonaje", back_populates="personaje")

class MisionPersonaje(Base):
    __tablename__ = 'misiones_personaje'
    personaje_id = Column(Integer, ForeignKey('personajes.id'), primary_key=True)
    mision_id = Column(Integer, ForeignKey('misiones.id'), primary_key=True)
    orden = Column(Integer)

    personaje = relationship("Personaje", back_populates="misiones")
    mision = relationship("Mision", back_populates="personajes")

# Crear tablas
Base.metadata.create_all(bind=engine)

# TDA Cola de Misiones
class ColaMisiones:
    def __init__(self, personaje_id: int, db):
        self.personaje_id = personaje_id
        self.db = db

    def enqueue(self, mision_id: int):
        total = self.db.query(MisionPersonaje).filter_by(personaje_id=self.personaje_id).count()
        nueva = MisionPersonaje(personaje_id=self.personaje_id, mision_id=mision_id, orden=total + 1)
        self.db.add(nueva)
        self.db.commit()

    def dequeue(self):
        primera = self.db.query(MisionPersonaje).filter_by(personaje_id=self.personaje_id).order_by(MisionPersonaje.orden).first()
        if primera:
            mision = self.db.query(Mision).get(primera.mision_id)
            mision.estado = EstadoMision.completada
            self.db.delete(primera)
            self.db.commit()
            return mision
        return None

    def first(self):
        return self.db.query(Mision).join(MisionPersonaje).filter(
            MisionPersonaje.personaje_id == self.personaje_id
        ).order_by(MisionPersonaje.orden).first()

    def is_empty(self):
        return self.db.query(MisionPersonaje).filter_by(personaje_id=self.personaje_id).count() == 0

    def size(self):
        return self.db.query(MisionPersonaje).filter_by(personaje_id=self.personaje_id).count()

# Esquemas de entrada
class PersonajeCreate(BaseModel):
    nombre: str

class MisionCreate(BaseModel):
    nombre: str
    descripcion: str
    experiencia: int

# Inicialización de FastAPI
app = FastAPI()

# Endpoints
@app.post("/personajes")
def crear_personaje(personaje: PersonajeCreate):
    db = SessionLocal()
    nuevo = Personaje(nombre=personaje.nombre)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    db.close()
    return nuevo

@app.post("/misiones")
def crear_mision(mision: MisionCreate):
    db = SessionLocal()
    nueva = Mision(
        nombre=mision.nombre,
        descripcion=mision.descripcion,
        experiencia=mision.experiencia
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    db.close()
    return nueva

@app.post("/personajes/{personaje_id}/misiones/{mision_id}")
def aceptar_mision(personaje_id: int, mision_id: int):
    db = SessionLocal()
    cola = ColaMisiones(personaje_id, db)
    cola.enqueue(mision_id)
    db.close()
    return {"mensaje": "Misión aceptada"}

@app.post("/personajes/{personaje_id}/completar")
def completar_mision(personaje_id: int):
    db = SessionLocal()
    cola = ColaMisiones(personaje_id, db)
    mision = cola.dequeue()
    db.close()
    if not mision:
        raise HTTPException(status_code=404, detail="No hay misiones en cola")
    return {"mensaje": f"Misión '{mision.nombre}' completada"}

@app.get("/personajes/{personaje_id}/misiones")
def listar_misiones(personaje_id: int):
    db = SessionLocal()
    misiones = (
        db.query(Mision)
        .join(MisionPersonaje)
        .filter(MisionPersonaje.personaje_id == personaje_id)
        .order_by(MisionPersonaje.orden)
        .all()
    )
    db.close()
    return misiones

@app.get("/personajes/{personaje_id}/size")
def obtener_tamano_cola(personaje_id: int):
    db = SessionLocal()
    cola = ColaMisiones(personaje_id, db)
    tamano = cola.size()
    db.close()
    return {"personaje_id": personaje_id, "tamano_cola": tamano}