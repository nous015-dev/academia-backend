
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime, timedelta
from typing import Optional
from io import BytesIO
import qrcode
import base64
import os

# =========================================================
# CONFIG
# =========================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./coliseu_fit.db")
QR_CATRACA = os.getenv("QR_CATRACA", "COLISEUFIT_ENTRADA_01")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

PLANOS = {
    30: {"nome": "Mensal", "valor": 125.0},
    180: {"nome": "Semestral", "valor": 720.0},
    365: {"nome": "Anual", "valor": 1320.0},
}

DEFAULT_PROMOCIONAL_DIAS = 15
DEFAULT_PROMOCIONAL_VALOR = 60.0

PROGRESSO_NIVEIS = [
    {"min": 0, "max": 10, "nivel": "inicial", "cor": "cinza", "titulo": "Começando", "mensagem": "Ótimo começo. O importante é seguir em movimento."},
    {"min": 11, "max": 25, "nivel": "consistente", "cor": "bronze", "titulo": "Consistência", "mensagem": "Você está criando um hábito forte. Continue assim."},
    {"min": 26, "max": 50, "nivel": "evoluindo", "cor": "azul", "titulo": "Evolução", "mensagem": "Seu ritmo já mostra disciplina de verdade."},
    {"min": 51, "max": 100, "nivel": "forte", "cor": "dourado", "titulo": "Foco total", "mensagem": "Seu compromisso inspira. Você está em outro nível."},
    {"min": 101, "max": 999999, "nivel": "premium", "cor": "premium", "titulo": "Elite Coliseu", "mensagem": "Sua frequência já virou identidade. Isso é mentalidade de campeão."},
]

TREINOS_PADRAO = {
    "A": {
        "titulo": "Treino A - Peito e tríceps",
        "exercicios": [
            "Supino reto - 4x12",
            "Supino inclinado - 3x12",
            "Crucifixo - 3x15",
            "Tríceps pulley - 4x12",
        ],
    },
    "B": {
        "titulo": "Treino B - Costas e bíceps",
        "exercicios": [
            "Puxada frente - 4x12",
            "Remada baixa - 3x12",
            "Rosca direta - 4x12",
            "Rosca alternada - 3x15",
        ],
    },
    "C": {
        "titulo": "Treino C - Pernas",
        "exercicios": [
            "Agachamento - 4x12",
            "Leg press - 4x12",
            "Cadeira extensora - 3x15",
            "Panturrilha - 4x20",
        ],
    },
    "D": {
        "titulo": "Treino D - Ombros e abdômen",
        "exercicios": [
            "Desenvolvimento - 4x12",
            "Elevação lateral - 3x15",
            "Elevação frontal - 3x12",
            "Abdominal infra - 4x20",
        ],
    },
    "E": {
        "titulo": "Treino E - Glúteos e posterior",
        "exercicios": [
            "Stiff - 4x12",
            "Mesa flexora - 4x12",
            "Glúteo máquina - 3x15",
            "Afundo - 3x12",
        ],
    },
}


class AlunoDB(Base):
    __tablename__ = "alunos"
    __table_args__ = (UniqueConstraint("cpf", name="uq_aluno_cpf"),)

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(120), nullable=False)
    telefone = Column(String(30), nullable=False)
    cpf = Column(String(14), nullable=False, index=True)
    vencimento = Column(String(10), nullable=False)
    valor_plano = Column(Float, nullable=False, default=0.0)
    plano_atual = Column(String(50), nullable=False, default="Mensal")
    foto_url = Column(Text, nullable=True)
    foto_base64 = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pagamentos = relationship("PagamentoDB", back_populates="aluno", cascade="all, delete-orphan")
    entradas = relationship("EntradaDB", back_populates="aluno", cascade="all, delete-orphan")
    leituras_avisos = relationship("AvisoLeituraDB", back_populates="aluno", cascade="all, delete-orphan")
    treinos = relationship("TreinoAlunoDB", back_populates="aluno", cascade="all, delete-orphan")


class PagamentoDB(Base):
    __tablename__ = "pagamentos"

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    nome = Column(String(120), nullable=False)
    plano = Column(String(50), nullable=False)
    valor = Column(Float, nullable=False)
    data_pagamento = Column(String(16), nullable=False)
    origem = Column(String(30), nullable=False, default="manual")
    status = Column(String(30), nullable=False, default="aprovado")

    aluno = relationship("AlunoDB", back_populates="pagamentos")


class EntradaDB(Base):
    __tablename__ = "entradas"

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    nome = Column(String(120), nullable=False)
    status = Column(String(30), nullable=False)
    motivo = Column(String(120), nullable=False)
    data_entrada = Column(String(16), nullable=False)

    aluno = relationship("AlunoDB", back_populates="entradas")


class AvisoDB(Base):
    __tablename__ = "avisos"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(150), nullable=False)
    mensagem = Column(Text, nullable=False)
    image_url = Column(Text, nullable=True)
    image_base64 = Column(Text, nullable=True)
    data = Column(String(16), nullable=False)


class AvisoLeituraDB(Base):
    __tablename__ = "aviso_leituras"
    __table_args__ = (UniqueConstraint("aluno_id", "aviso_id", name="uq_aluno_aviso"),)

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False)
    aviso_id = Column(Integer, ForeignKey("avisos.id"), nullable=False)
    lido_em = Column(String(16), nullable=False)

    aluno = relationship("AlunoDB", back_populates="leituras_avisos")


class ConfigDB(Base):
    __tablename__ = "configuracoes"

    id = Column(Integer, primary_key=True, index=True)
    chave = Column(String(80), unique=True, nullable=False, index=True)
    valor = Column(String(255), nullable=False)


class TreinoAlunoDB(Base):
    __tablename__ = "treinos_aluno"

    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    codigo = Column(String(1), nullable=False)
    titulo = Column(String(150), nullable=False)
    exercicios = Column(Text, nullable=False)
    ordem = Column(Integer, nullable=False, default=0)

    aluno = relationship("AlunoDB", back_populates="treinos")


Base.metadata.create_all(bind=engine)


def agora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def hoje() -> datetime:
    return datetime.now()


def normalizar_cpf(cpf: str) -> str:
    return "".join(ch for ch in (cpf or "") if ch.isdigit())


def formatar_cpf(cpf: str) -> str:
    dig = normalizar_cpf(cpf)
    if len(dig) != 11:
        return cpf
    return f"{dig[:3]}.{dig[3:6]}.{dig[6:9]}-{dig[9:]}"


def validar_cpf_basico(cpf: str) -> bool:
    dig = normalizar_cpf(cpf)
    return len(dig) == 11


def get_config(db, chave: str, default: str) -> str:
    item = db.query(ConfigDB).filter(ConfigDB.chave == chave).first()
    if not item:
        item = ConfigDB(chave=chave, valor=default)
        db.add(item)
        db.commit()
        db.refresh(item)
    return item.valor


def set_config(db, chave: str, valor: str) -> str:
    item = db.query(ConfigDB).filter(ConfigDB.chave == chave).first()
    if not item:
        item = ConfigDB(chave=chave, valor=valor)
        db.add(item)
    else:
        item.valor = valor
    db.commit()
    db.refresh(item)
    return item.valor


def valor_promocional_atual(db) -> float:
    try:
        return float(get_config(db, "plano_promocional_valor", str(DEFAULT_PROMOCIONAL_VALOR)))
    except Exception:
        return DEFAULT_PROMOCIONAL_VALOR


def info_plano_por_dias(dias: int, db=None) -> dict:
    if dias == DEFAULT_PROMOCIONAL_DIAS:
        return {"nome": "Promocional", "valor": valor_promocional_atual(db) if db is not None else DEFAULT_PROMOCIONAL_VALOR}
    return PLANOS.get(dias, {"nome": f"{dias} dias", "valor": 0.0})


def obter_status_por_vencimento(vencimento_str: str) -> str:
    try:
        vencimento = datetime.strptime(vencimento_str, "%Y-%m-%d")
    except Exception:
        return "atrasado"
    return "em dia" if hoje().date() <= vencimento.date() else "atrasado"


def buscar_aluno_por_id(db, aluno_id: int) -> Optional[AlunoDB]:
    return db.query(AlunoDB).filter(AlunoDB.id == aluno_id).first()


def buscar_aluno_por_cpf(db, cpf: str) -> Optional[AlunoDB]:
    cpf_norm = normalizar_cpf(cpf)
    return db.query(AlunoDB).filter(AlunoDB.cpf == cpf_norm).first()


def gerar_qr_base64(texto: str) -> str:
    img = qrcode.make(texto)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    base64_img = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{base64_img}"


def garantir_treinos_padrao(db, aluno_id: int):
    existentes = db.query(TreinoAlunoDB).filter(TreinoAlunoDB.aluno_id == aluno_id).count()
    if existentes > 0:
        return
    ordem = 1
    for codigo, dados in TREINOS_PADRAO.items():
        treino = TreinoAlunoDB(
            aluno_id=aluno_id,
            codigo=codigo,
            titulo=dados["titulo"],
            exercicios="|".join(dados["exercicios"]),
            ordem=ordem,
        )
        db.add(treino)
        ordem += 1
    db.commit()


def calcular_progresso(total_entradas: int) -> dict:
    nivel_atual = PROGRESSO_NIVEIS[-1]
    for item in PROGRESSO_NIVEIS:
        if item["min"] <= total_entradas <= item["max"]:
            nivel_atual = item
            break

    proxima_meta = None
    for item in PROGRESSO_NIVEIS:
        if total_entradas < item["min"]:
            proxima_meta = item["min"]
            break

    return {
        "total_entradas": total_entradas,
        "nivel": nivel_atual["nivel"],
        "cor": nivel_atual["cor"],
        "titulo": nivel_atual["titulo"],
        "mensagem": nivel_atual["mensagem"],
        "proxima_meta": proxima_meta,
        "progresso_percent": min(100, int((total_entradas / 200) * 100)) if total_entradas > 0 else 0,
        "metas": [10, 25, 50, 100, 200],
    }


def pagamentos_por_periodo(db, periodo: str):
    agora = datetime.now()
    if periodo == "semana":
        inicio = agora - timedelta(days=7)
    elif periodo == "quinzena":
        inicio = agora - timedelta(days=15)
    elif periodo == "mes":
        inicio = agora - timedelta(days=30)
    else:
        return db.query(PagamentoDB).order_by(PagamentoDB.id.desc()).all()

    pagamentos = db.query(PagamentoDB).all()
    filtrados = []
    for p in pagamentos:
        try:
            data = datetime.strptime(p.data_pagamento, "%Y-%m-%d %H:%M")
            if data >= inicio:
                filtrados.append(p)
        except Exception:
            continue
    return list(sorted(filtrados, key=lambda x: x.id, reverse=True))


def contar_avisos_nao_lidos(db, aluno_id: int) -> int:
    total_avisos = db.query(AvisoDB).count()
    lidos = db.query(AvisoLeituraDB).filter(AvisoLeituraDB.aluno_id == aluno_id).count()
    return max(0, total_avisos - lidos)


def aluno_to_dict(db, aluno: AlunoDB) -> dict:
    total_entradas_liberadas = (
        db.query(EntradaDB)
        .filter(EntradaDB.aluno_id == aluno.id, EntradaDB.status == "liberado")
        .count()
    )
    ultimo_pagamento = (
        db.query(PagamentoDB)
        .filter(PagamentoDB.aluno_id == aluno.id)
        .order_by(PagamentoDB.id.desc())
        .first()
    )
    ultimo_acesso = (
        db.query(EntradaDB)
        .filter(EntradaDB.aluno_id == aluno.id)
        .order_by(EntradaDB.id.desc())
        .first()
    )
    return {
        "id": aluno.id,
        "nome": aluno.nome,
        "telefone": aluno.telefone,
        "cpf": formatar_cpf(aluno.cpf),
        "vencimento": aluno.vencimento,
        "valor_plano": float(aluno.valor_plano),
        "plano_atual": aluno.plano_atual,
        "status": obter_status_por_vencimento(aluno.vencimento),
        "foto_url": aluno.foto_url,
        "foto_base64": aluno.foto_base64,
        "total_entradas": total_entradas_liberadas,
        "ultimo_pagamento": None if not ultimo_pagamento else {
            "id": ultimo_pagamento.id,
            "plano": ultimo_pagamento.plano,
            "valor": float(ultimo_pagamento.valor),
            "data_pagamento": ultimo_pagamento.data_pagamento,
            "origem": ultimo_pagamento.origem,
            "status": ultimo_pagamento.status,
        },
        "ultimo_acesso": None if not ultimo_acesso else {
            "id": ultimo_acesso.id,
            "status": ultimo_acesso.status,
            "motivo": ultimo_acesso.motivo,
            "data_entrada": ultimo_acesso.data_entrada,
        },
    }


def calcular_resumo(db) -> dict:
    alunos = db.query(AlunoDB).all()
    lista = [aluno_to_dict(db, a) for a in alunos]
    total = len(lista)
    em_dia = len([a for a in lista if a["status"] == "em dia"])
    atrasados = len([a for a in lista if a["status"] == "atrasado"])
    faturamento_real = sum(float(a.get("valor_plano", 0)) for a in lista if a["status"] == "em dia")
    faturamento_potencial = sum(float(a.get("valor_plano", 0)) for a in lista)
    inadimplencia_valor = faturamento_potencial - faturamento_real
    return {
        "total_alunos": total,
        "em_dia": em_dia,
        "atrasados": atrasados,
        "faturamento_real": faturamento_real,
        "faturamento_potencial": faturamento_potencial,
        "inadimplencia_valor": inadimplencia_valor,
    }


def listar_alunos_filtrados(db, status: Optional[str] = None, plano: Optional[str] = None):
    alunos = db.query(AlunoDB).order_by(AlunoDB.id.asc()).all()
    lista = [aluno_to_dict(db, a) for a in alunos]
    if status:
        lista = [a for a in lista if a["status"].lower() == status.lower()]
    if plano:
        lista = [a for a in lista if (a["plano_atual"] or "").lower() == plano.lower()]
    return lista


app = FastAPI(title="Coliseu Fit API", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "API do Coliseu Fit funcionando"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/aluno/login")
def login_aluno(cpf: str = Query(...)):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_cpf(db, cpf)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return {
            "mensagem": "Login realizado com sucesso",
            "aluno": aluno_to_dict(db, aluno),
            "avisos_nao_lidos": contar_avisos_nao_lidos(db, aluno.id),
        }
    finally:
        db.close()


@app.get("/aluno/cpf/{cpf}")
def obter_aluno_por_cpf(cpf: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_cpf(db, cpf)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return aluno_to_dict(db, aluno)
    finally:
        db.close()


@app.post("/alunos")
def criar_aluno(nome: str, telefone: str, cpf: str, dias_plano: int = 30):
    db = SessionLocal()
    try:
        cpf_norm = normalizar_cpf(cpf)
        if not nome.strip():
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        if not telefone.strip():
            raise HTTPException(status_code=400, detail="Telefone é obrigatório")
        if not validar_cpf_basico(cpf_norm):
            raise HTTPException(status_code=400, detail="CPF inválido")
        if buscar_aluno_por_cpf(db, cpf_norm):
            raise HTTPException(status_code=400, detail="CPF já cadastrado")

        plano_info = info_plano_por_dias(dias_plano, db)
        vencimento = hoje() + timedelta(days=dias_plano)
        aluno = AlunoDB(
            nome=nome.strip(),
            telefone=telefone.strip(),
            cpf=cpf_norm,
            vencimento=vencimento.strftime("%Y-%m-%d"),
            valor_plano=plano_info["valor"],
            plano_atual=plano_info["nome"],
        )
        db.add(aluno)
        db.commit()
        db.refresh(aluno)
        garantir_treinos_padrao(db, aluno.id)
        return {"mensagem": "Aluno criado com sucesso", "aluno": aluno_to_dict(db, aluno)}
    finally:
        db.close()


@app.get("/alunos")
def listar_alunos(status: Optional[str] = Query(default=None), plano: Optional[str] = Query(default=None)):
    db = SessionLocal()
    try:
        return listar_alunos_filtrados(db, status=status, plano=plano)
    finally:
        db.close()


@app.get("/aluno/{aluno_id}")
def detalhar_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return aluno_to_dict(db, aluno)
    finally:
        db.close()


@app.put("/alunos/{aluno_id}")
def editar_aluno(aluno_id: int, nome: str, telefone: str, cpf: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        cpf_norm = normalizar_cpf(cpf)
        if not validar_cpf_basico(cpf_norm):
            raise HTTPException(status_code=400, detail="CPF inválido")

        outro = buscar_aluno_por_cpf(db, cpf_norm)
        if outro and outro.id != aluno.id:
            raise HTTPException(status_code=400, detail="CPF já cadastrado para outro aluno")

        aluno.nome = nome.strip()
        aluno.telefone = telefone.strip()
        aluno.cpf = cpf_norm
        db.commit()
        db.refresh(aluno)
        return {"mensagem": "Aluno atualizado com sucesso", "aluno": aluno_to_dict(db, aluno)}
    finally:
        db.close()


@app.delete("/alunos/{aluno_id}")
def excluir_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        db.delete(aluno)
        db.commit()
        return {"mensagem": "Aluno excluído com sucesso"}
    finally:
        db.close()


@app.put("/alunos/{aluno_id}/foto")
def atualizar_foto_aluno(aluno_id: int, foto_url: Optional[str] = None, foto_base64: Optional[str] = None):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        aluno.foto_url = foto_url
        aluno.foto_base64 = foto_base64
        db.commit()
        db.refresh(aluno)
        return {"mensagem": "Foto atualizada com sucesso", "aluno": aluno_to_dict(db, aluno)}
    finally:
        db.close()


@app.get("/aluno/{aluno_id}/treinos")
def treinos_do_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        garantir_treinos_padrao(db, aluno_id)
        treinos = db.query(TreinoAlunoDB).filter(TreinoAlunoDB.aluno_id == aluno_id).order_by(TreinoAlunoDB.ordem.asc()).all()
        return [{"codigo": t.codigo, "titulo": t.titulo, "exercicios": [e for e in t.exercicios.split("|") if e], "ordem": t.ordem} for t in treinos]
    finally:
        db.close()


@app.put("/pagar/{aluno_id}")
def registrar_pagamento(aluno_id: int, dias: int = 30, valor: Optional[float] = None):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        plano_info = info_plano_por_dias(dias, db)
        valor_final = valor if valor is not None else plano_info["valor"]
        vencimento_atual = datetime.strptime(aluno.vencimento, "%Y-%m-%d")
        base = vencimento_atual if vencimento_atual.date() >= hoje().date() else hoje()
        novo_vencimento = base + timedelta(days=dias)

        aluno.vencimento = novo_vencimento.strftime("%Y-%m-%d")
        aluno.plano_atual = plano_info["nome"]
        aluno.valor_plano = float(valor_final)

        pagamento = PagamentoDB(
            aluno_id=aluno.id, nome=aluno.nome, plano=aluno.plano_atual,
            valor=float(valor_final), data_pagamento=agora_str(),
            origem="manual", status="aprovado"
        )
        db.add(pagamento)
        db.commit()
        db.refresh(aluno)
        db.refresh(pagamento)
        return {
            "mensagem": "Pagamento registrado com sucesso",
            "aluno": aluno_to_dict(db, aluno),
            "pagamento": {
                "id": pagamento.id, "aluno_id": pagamento.aluno_id,
                "nome": pagamento.nome, "plano": pagamento.plano, "valor": pagamento.valor,
                "data_pagamento": pagamento.data_pagamento, "origem": pagamento.origem, "status": pagamento.status,
            },
        }
    finally:
        db.close()


@app.put("/aluno/{aluno_id}/regularizar")
def regularizar_pagamento_aluno(aluno_id: int, dias: int = 30, valor: Optional[float] = None):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        plano_info = info_plano_por_dias(dias, db)
        valor_final = valor if valor is not None else plano_info["valor"]
        novo_vencimento = hoje() + timedelta(days=dias)

        aluno.vencimento = novo_vencimento.strftime("%Y-%m-%d")
        aluno.plano_atual = plano_info["nome"]
        aluno.valor_plano = float(valor_final)

        pagamento = PagamentoDB(
            aluno_id=aluno.id, nome=aluno.nome, plano=aluno.plano_atual,
            valor=float(valor_final), data_pagamento=agora_str(),
            origem="app_aluno", status="aprovado"
        )
        db.add(pagamento)
        db.commit()
        db.refresh(aluno)
        db.refresh(pagamento)
        return {
            "mensagem": "Pagamento realizado com sucesso. Plano regularizado.",
            "aluno": aluno_to_dict(db, aluno),
            "pagamento": {
                "id": pagamento.id, "aluno_id": pagamento.aluno_id,
                "nome": pagamento.nome, "plano": pagamento.plano, "valor": pagamento.valor,
                "data_pagamento": pagamento.data_pagamento, "origem": pagamento.origem, "status": pagamento.status,
            },
        }
    finally:
        db.close()


@app.get("/config/planos")
def obter_config_planos():
    db = SessionLocal()
    try:
        return {
            "mensal": PLANOS[30]["valor"],
            "semestral": PLANOS[180]["valor"],
            "anual": PLANOS[365]["valor"],
            "promocional": valor_promocional_atual(db),
        }
    finally:
        db.close()


@app.put("/config/planos/promocional")
def atualizar_plano_promocional(valor: float):
    db = SessionLocal()
    try:
        if valor < 0:
            raise HTTPException(status_code=400, detail="Valor inválido")
        novo = set_config(db, "plano_promocional_valor", str(valor))
        return {"mensagem": "Valor promocional atualizado com sucesso", "promocional": float(novo)}
    finally:
        db.close()


@app.put("/alunos/{aluno_id}/teste/vencimento")
def ajustar_vencimento_teste(aluno_id: int, dias: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        novo_vencimento = hoje() + timedelta(days=dias)
        aluno.vencimento = novo_vencimento.strftime("%Y-%m-%d")
        db.commit()
        db.refresh(aluno)
        return {"mensagem": "Vencimento ajustado para teste", "aluno": aluno_to_dict(db, aluno)}
    finally:
        db.close()


@app.get("/historico")
def listar_historico():
    db = SessionLocal()
    try:
        pagamentos = db.query(PagamentoDB).order_by(PagamentoDB.id.desc()).all()
        return [{"id": p.id, "aluno_id": p.aluno_id, "nome": p.nome, "plano": p.plano, "valor": p.valor, "data_pagamento": p.data_pagamento, "origem": p.origem, "status": p.status} for p in pagamentos]
    finally:
        db.close()


@app.get("/aluno/{aluno_id}/pagamentos")
def historico_pagamentos_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        pagamentos = db.query(PagamentoDB).filter(PagamentoDB.aluno_id == aluno_id).order_by(PagamentoDB.id.desc()).all()
        return [{"id": p.id, "aluno_id": p.aluno_id, "nome": p.nome, "plano": p.plano, "valor": p.valor, "data_pagamento": p.data_pagamento, "origem": p.origem, "status": p.status} for p in pagamentos]
    finally:
        db.close()


@app.get("/historico/filtro")
def historico_filtrado(periodo: str = "mes"):
    db = SessionLocal()
    try:
        lista = pagamentos_por_periodo(db, periodo)
        total = sum(float(p.valor) for p in lista)
        return {"periodo": periodo, "total_registros": len(lista), "faturamento": total, "pagamentos": [{"id": p.id, "aluno_id": p.aluno_id, "nome": p.nome, "plano": p.plano, "valor": p.valor, "data_pagamento": p.data_pagamento, "origem": p.origem, "status": p.status} for p in lista]}
    finally:
        db.close()


@app.get("/validar/{aluno_id}")
def validar_acesso(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        status = obter_status_por_vencimento(aluno.vencimento)
        return {"acesso": "liberado" if status == "em dia" else "bloqueado", "status_aluno": status, "mensagem": "Acesso liberado" if status == "em dia" else "Pagamento pendente. Regularize sua mensalidade."}
    finally:
        db.close()


@app.post("/entrada/{aluno_id}")
def registrar_entrada(aluno_id: int, codigo_qr: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        status_aluno = obter_status_por_vencimento(aluno.vencimento)
        codigo_qr = (codigo_qr or "").strip()

        if status_aluno != "em dia":
            item = EntradaDB(aluno_id=aluno.id, nome=aluno.nome, status="bloqueado", motivo="pagamento pendente", data_entrada=agora_str())
            db.add(item)
            db.commit()
            return {"acesso": "bloqueado", "mensagem": "Pagamento pendente. Regularize sua mensalidade.", "ir_para_pagamento": True}

        if codigo_qr != QR_CATRACA.strip():
            item = EntradaDB(aluno_id=aluno.id, nome=aluno.nome, status="bloqueado", motivo="qr inválido", data_entrada=agora_str())
            db.add(item)
            db.commit()
            return {"acesso": "bloqueado", "mensagem": "QR da catraca inválido.", "ir_para_pagamento": False}

        item = EntradaDB(aluno_id=aluno.id, nome=aluno.nome, status="liberado", motivo="entrada autorizada", data_entrada=agora_str())
        db.add(item)
        db.commit()

        total_entradas = db.query(EntradaDB).filter(EntradaDB.aluno_id == aluno.id, EntradaDB.status == "liberado").count()
        return {"acesso": "liberado", "mensagem": "Acesso liberado. Bom treino!", "total_entradas": total_entradas, "progresso": calcular_progresso(total_entradas)}
    finally:
        db.close()


@app.get("/entradas")
def listar_entradas():
    db = SessionLocal()
    try:
        entradas = db.query(EntradaDB).order_by(EntradaDB.id.desc()).all()
        return [{"id": e.id, "aluno_id": e.aluno_id, "nome": e.nome, "status": e.status, "motivo": e.motivo, "data_entrada": e.data_entrada} for e in entradas]
    finally:
        db.close()


@app.get("/aluno/{aluno_id}/entradas")
def entradas_do_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        entradas = db.query(EntradaDB).filter(EntradaDB.aluno_id == aluno_id).order_by(EntradaDB.id.desc()).all()
        return [{"id": e.id, "aluno_id": e.aluno_id, "nome": e.nome, "status": e.status, "motivo": e.motivo, "data_entrada": e.data_entrada} for e in entradas]
    finally:
        db.close()


@app.get("/aluno/{aluno_id}/progresso")
def progresso_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        total_entradas = db.query(EntradaDB).filter(EntradaDB.aluno_id == aluno_id, EntradaDB.status == "liberado").count()
        return calcular_progresso(total_entradas)
    finally:
        db.close()


@app.get("/catraca/qr")
def obter_qr_catraca():
    return {"codigo": QR_CATRACA, "qr_image_base64": gerar_qr_base64(QR_CATRACA)}




class AvisoCreate(BaseModel):
    titulo: str
    mensagem: str
    image_url: Optional[str] = None
    image_base64: Optional[str] = None

@app.post("/avisos")
def criar_aviso(payload: AvisoCreate):
    db = SessionLocal()
    try:
        aviso = AvisoDB(
            titulo=payload.titulo.strip(),
            mensagem=payload.mensagem.strip(),
            image_url=(payload.image_url or None),
            image_base64=(payload.image_base64 or None),
            data=agora_str(),
        )
        db.add(aviso)
        db.commit()
        db.refresh(aviso)
        return {
            "ok": True,
            "mensagem": "Aviso criado com sucesso",
            "aviso": {
                "id": aviso.id,
                "titulo": aviso.titulo,
                "mensagem": aviso.mensagem,
                "image_url": aviso.image_url,
                "image_base64": aviso.image_base64,
                "data": aviso.data,
            },
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/avisos")
def listar_avisos():
    db = SessionLocal()
    try:
        avisos = db.query(AvisoDB).order_by(AvisoDB.id.desc()).all()
        return [{"id": a.id, "titulo": a.titulo, "mensagem": a.mensagem, "image_url": a.image_url, "image_base64": a.image_base64, "data": a.data} for a in avisos]
    finally:
        db.close()


@app.get("/aluno/{aluno_id}/avisos")
def listar_avisos_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        leituras = db.query(AvisoLeituraDB).filter(AvisoLeituraDB.aluno_id == aluno_id).all()
        lidos_map = {l.aviso_id: l.lido_em for l in leituras}
        avisos = db.query(AvisoDB).order_by(AvisoDB.id.desc()).all()
        return {
            "nao_lidos": contar_avisos_nao_lidos(db, aluno_id),
            "avisos": [{"id": a.id, "titulo": a.titulo, "mensagem": a.mensagem, "image_url": a.image_url, "image_base64": a.image_base64, "data": a.data, "lido": a.id in lidos_map, "lido_em": lidos_map.get(a.id)} for a in avisos],
        }
    finally:
        db.close()


@app.post("/aluno/{aluno_id}/avisos/{aviso_id}/ler")
def marcar_aviso_lido(aluno_id: int, aviso_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        aviso = db.query(AvisoDB).filter(AvisoDB.id == aviso_id).first()
        if not aviso:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")
        leitura = db.query(AvisoLeituraDB).filter(AvisoLeituraDB.aluno_id == aluno_id, AvisoLeituraDB.aviso_id == aviso_id).first()
        if not leitura:
            leitura = AvisoLeituraDB(aluno_id=aluno_id, aviso_id=aviso_id, lido_em=agora_str())
            db.add(leitura)
            db.commit()
        return {"mensagem": "Aviso marcado como lido", "nao_lidos": contar_avisos_nao_lidos(db, aluno_id)}
    finally:
        db.close()


@app.delete("/avisos/{aviso_id}")
def excluir_aviso(aviso_id: int):
    db = SessionLocal()
    try:
        aviso = db.query(AvisoDB).filter(AvisoDB.id == aviso_id).first()
        if not aviso:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")
        db.delete(aviso)
        db.commit()
        return {"mensagem": "Aviso excluído com sucesso"}
    finally:
        db.close()


@app.get("/relatorio/resumo")
def relatorio_resumo():
    db = SessionLocal()
    try:
        return calcular_resumo(db)
    finally:
        db.close()


@app.get("/relatorio/planos")
def relatorio_planos():
    db = SessionLocal()
    try:
        alunos = db.query(AlunoDB).all()
        resumo = {"Mensal": 0, "Semestral": 0, "Anual": 0, "Promocional": 0}
        for aluno in alunos:
            plano = aluno.plano_atual or ""
            if plano in resumo:
                resumo[plano] += 1
        return resumo
    finally:
        db.close()


@app.get("/relatorio/alunos")
def relatorio_alunos(status: Optional[str] = Query(default=None), plano: Optional[str] = Query(default=None)):
    db = SessionLocal()
    try:
        lista = listar_alunos_filtrados(db, status=status, plano=plano)
        return {"total": len(lista), "alunos": lista}
    finally:
        db.close()


@app.get("/relatorio/vendas")
def relatorio_vendas(periodo: str = "mes"):
    db = SessionLocal()
    try:
        pagamentos = pagamentos_por_periodo(db, periodo)
        total = sum(float(p.valor) for p in pagamentos)
        resumo = calcular_resumo(db)
        return {"periodo": periodo, "faturamento_obtido": total, "faturamento_real_atual": resumo["faturamento_real"], "faturamento_potencial": resumo["faturamento_potencial"], "inadimplencia_valor": resumo["inadimplencia_valor"], "pagamentos": [{"id": p.id, "aluno_id": p.aluno_id, "nome": p.nome, "plano": p.plano, "valor": p.valor, "data_pagamento": p.data_pagamento, "origem": p.origem, "status": p.status} for p in pagamentos]}
    finally:
        db.close()
