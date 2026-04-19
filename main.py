
import base64
import os
import re
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional, Literal

import qrcode
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

APP_TITLE = "Coliseu Fit API"
APP_VERSION = "5.0.0"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./coliseu_fit.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

QR_CATRACA = os.getenv("QR_CATRACA", "CATRACA_ACADEMIA_01").strip()
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "Coliseufit")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Coliseu_fit2026")
INFINITEPAY_HANDLE = os.getenv("INFINITEPAY_HANDLE", "aylen-65425645-v40").strip()

PAYMENT_LINK_MENSAL = os.getenv("PAYMENT_LINK_MENSAL", "https://link.infinitepay.io/aylen-65425645-v40/VC1D-JncUSFq47-125,00").strip()
PAYMENT_LINK_SEMESTRAL = os.getenv("PAYMENT_LINK_SEMESTRAL", "https://link.infinitepay.io/aylen-65425645-v40/VC1D-1HCUNRg7PL-720,00").strip()
PAYMENT_LINK_ANUAL = os.getenv("PAYMENT_LINK_ANUAL", "https://link.infinitepay.io/aylen-65425645-v40/VC1D-7fCwy6Ol2L-1320,00").strip()
PAYMENT_LINK_PROMOCIONAL = os.getenv("PAYMENT_LINK_PROMOCIONAL", "").strip()

MENSAL_VALOR = 125.0
SEMESTRAL_VALOR = 720.0
ANUAL_VALOR = 1320.0
PROMOCIONAL_VALOR_PADRAO = 80.90
PROMOCIONAL_DIAS_PADRAO = 30

PLANOS_FIXOS = {
    30: {"nome": "Mensal", "valor": MENSAL_VALOR},
    180: {"nome": "Semestral", "valor": SEMESTRAL_VALOR},
    365: {"nome": "Anual", "valor": ANUAL_VALOR},
}

class ConfigDB(Base):
    __tablename__ = "configuracoes"
    id = Column(Integer, primary_key=True, index=True)
    chave = Column(String, unique=True, nullable=False)
    valor = Column(Text, nullable=False)


class AlunoDB(Base):
    __tablename__ = "alunos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    telefone = Column(String, nullable=True)
    cpf = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=True)
    sexo = Column(String, nullable=True)

    status_manual = Column(String, default="pendente")  # pendente / em_dia / atrasado / inativo
    plano_nome = Column(String, nullable=True)
    valor_plano = Column(Float, default=0.0)
    desconto_percentual = Column(Float, default=0.0)
    vencimento = Column(String, nullable=True)  # YYYY-MM-DD

    foto_url = Column(Text, nullable=True)
    foto_base64 = Column(Text, nullable=True)
    data_cadastro = Column(String, nullable=True)

    status_cliente_raw = Column(String, nullable=True)
    status_contrato_raw = Column(String, nullable=True)

    valor_personalizado = Column(Float, nullable=True)
    beneficio_ativo = Column(Boolean, default=True)
    valor_padrao_plano = Column(Float, nullable=True)
    origem_valor = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class PagamentoDB(Base):
    __tablename__ = "pagamentos"
    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    plano_nome = Column(String, nullable=False)
    valor = Column(Float, default=0.0)
    dias = Column(Integer, nullable=False)
    status = Column(String, default="pago")
    origem = Column(String, default="manual")
    link_pagamento = Column(Text, nullable=True)
    data_pagamento = Column(DateTime, default=datetime.utcnow)
    vencimento_anterior = Column(String, nullable=True)
    novo_vencimento = Column(String, nullable=True)

    aluno = relationship("AlunoDB")

class AvisoDB(Base):
    __tablename__ = "avisos"
    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String, nullable=False)
    mensagem = Column(Text, nullable=False)
    imagem_base64 = Column(Text, nullable=True)
    data = Column(DateTime, default=datetime.utcnow)

class AvisoLeituraDB(Base):
    __tablename__ = "avisos_leituras"
    id = Column(Integer, primary_key=True, index=True)
    aviso_id = Column(Integer, ForeignKey("avisos.id"), nullable=False, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    lido = Column(Boolean, default=True)
    data = Column(DateTime, default=datetime.utcnow)

class TreinoDB(Base):
    __tablename__ = "treinos"
    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    categoria = Column(String, nullable=False)  # A/B/C/D/E
    titulo = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)
    exercicios = Column(Text, nullable=True)  # texto puro separado por quebras de linha
    video_url = Column(Text, nullable=True)


class EntradaDB(Base):
    __tablename__ = "entradas"
    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer, ForeignKey("alunos.id"), nullable=False, index=True)
    nome = Column(String, nullable=False)
    status = Column(String, nullable=False)  # liberado / bloqueado
    motivo = Column(String, nullable=False)
    data_entrada = Column(DateTime, default=datetime.utcnow)



def ensure_schema_updates():
    insp = inspect(engine)

    if "alunos" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("alunos")}
        alter_cmds = []

        expected_columns = {
            "email": "ALTER TABLE alunos ADD COLUMN email VARCHAR(255)",
            "sexo": "ALTER TABLE alunos ADD COLUMN sexo VARCHAR(50)",
            "status_manual": "ALTER TABLE alunos ADD COLUMN status_manual VARCHAR(20) DEFAULT 'pendente'",
            "plano_nome": "ALTER TABLE alunos ADD COLUMN plano_nome VARCHAR(100)",
            "valor_plano": "ALTER TABLE alunos ADD COLUMN valor_plano FLOAT DEFAULT 0",
            "desconto_percentual": "ALTER TABLE alunos ADD COLUMN desconto_percentual FLOAT DEFAULT 0",
            "vencimento": "ALTER TABLE alunos ADD COLUMN vencimento VARCHAR(20)",
            "foto_url": "ALTER TABLE alunos ADD COLUMN foto_url TEXT",
            "foto_base64": "ALTER TABLE alunos ADD COLUMN foto_base64 TEXT",
            "data_cadastro": "ALTER TABLE alunos ADD COLUMN data_cadastro VARCHAR(50)",
            "status_cliente_raw": "ALTER TABLE alunos ADD COLUMN status_cliente_raw VARCHAR(50)",
            "status_contrato_raw": "ALTER TABLE alunos ADD COLUMN status_contrato_raw VARCHAR(50)",
            "valor_personalizado": "ALTER TABLE alunos ADD COLUMN valor_personalizado FLOAT",
            "beneficio_ativo": "ALTER TABLE alunos ADD COLUMN beneficio_ativo BOOLEAN DEFAULT 1",
            "valor_padrao_plano": "ALTER TABLE alunos ADD COLUMN valor_padrao_plano FLOAT",
            "origem_valor": "ALTER TABLE alunos ADD COLUMN origem_valor VARCHAR(50)",
            "created_at": "ALTER TABLE alunos ADD COLUMN created_at TIMESTAMP",
            "updated_at": "ALTER TABLE alunos ADD COLUMN updated_at TIMESTAMP",
        }

        for col_name, cmd in expected_columns.items():
            if col_name not in cols:
                alter_cmds.append(cmd)

        if alter_cmds:
            with engine.begin() as conn:
                for cmd in alter_cmds:
                    conn.execute(text(cmd))

ensure_schema_updates()

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------
# Models
# ----------------------
class AdminLoginBody(BaseModel):
    login: str
    senha: str

class AlunoCreate(BaseModel):
    nome: str
    telefone: Optional[str] = None
    cpf: str
    email: Optional[str] = None
    sexo: Optional[str] = None
    plano_nome: Optional[str] = None
    dias_plano: Optional[int] = None
    desconto_percentual: Optional[float] = 0.0

class AlunoAdminUpdate(BaseModel):
    nome: str
    telefone: Optional[str] = None
    cpf: str
    email: Optional[str] = None
    sexo: Optional[str] = None
    plano_nome: Optional[str] = None
    valor_plano: Optional[float] = None
    desconto_percentual: Optional[float] = None
    vencimento: Optional[str] = None
    status_manual: Optional[Literal["pendente", "em_dia", "atrasado", "inativo"]] = None

class AlunoSelfUpdate(BaseModel):
    nome: str
    telefone: Optional[str] = None

class FotoAlunoBody(BaseModel):
    foto_url: Optional[str] = None
    foto_base64: Optional[str] = None

class AvisoCreate(BaseModel):
    titulo: str
    mensagem: str
    imagem_base64: Optional[str] = None
    image_base64: Optional[str] = None

class AvisoLidoBody(BaseModel):
    aluno_id: int

class TreinoCreate(BaseModel):
    aluno_id: int
    categoria: Literal["A", "B", "C", "D", "E"]
    titulo: str
    descricao: Optional[str] = None
    exercicios: Optional[str] = None
    video_url: Optional[str] = None


class DescontoBody(BaseModel):
    desconto_percentual: float = Field(0, ge=0, le=100)

class PagamentoBody(BaseModel):
    plano: Literal["mensal", "semestral", "anual", "promocional"]
    valor: Optional[float] = None
    dias: Optional[int] = None
    origem: Literal["manual", "aluno_link"] = "manual"

class EntradaBody(BaseModel):
    codigo_qr: str

class PromocionalConfigBody(BaseModel):
    valor: float = Field(..., gt=0)
    dias: int = Field(..., gt=0)

class PaymentLinksBody(BaseModel):
    mensal: Optional[str] = None
    semestral: Optional[str] = None
    anual: Optional[str] = None
    promocional: Optional[str] = None

# ----------------------
# Helpers
# ----------------------
def hoje() -> date:
    return date.today()

def hoje_str() -> str:
    return hoje().strftime("%Y-%m-%d")

def agora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")

def validar_cpf(cpf: str) -> bool:
    cpf = only_digits(cpf)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False

    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    dig1 = (soma * 10 % 11) % 10

    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    dig2 = (soma * 10 % 11) % 10

    return dig1 == int(cpf[9]) and dig2 == int(cpf[10])

def parse_date_safe(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def dias_atraso(vencimento: Optional[str]) -> int:
    venc = parse_date_safe(vencimento)
    if not venc:
        return 0
    return (hoje() - venc).days

def obter_status_por_regras(aluno: AlunoDB) -> str:
    manual = (aluno.status_manual or "").strip().lower()

    # cadastro novo sem pagamento inicial
    if manual == "pendente" or not aluno.vencimento:
        return "pendente"

    atraso = dias_atraso(aluno.vencimento)

    if atraso <= 0:
        return "em_dia"
    if atraso > 30:
        return "inativo"
    return "atrasado"

def info_plano(db, plano_key: str, valor_override: Optional[float] = None, dias_override: Optional[int] = None):
    plano_key = (plano_key or "").strip().lower()
    promocional_valor = float(get_config(db, "promocional_valor", str(PROMOCIONAL_VALOR_PADRAO)))
    promocional_dias = int(get_config(db, "promocional_dias", str(PROMOCIONAL_DIAS_PADRAO)))

    tabela = {
        "mensal": {"nome": "Mensal", "valor": MENSAL_VALOR, "dias": 30},
        "semestral": {"nome": "Semestral", "valor": SEMESTRAL_VALOR, "dias": 180},
        "anual": {"nome": "Anual", "valor": ANUAL_VALOR, "dias": 365},
        "promocional": {"nome": "Promocional", "valor": promocional_valor, "dias": promocional_dias},
    }
    item = tabela.get(plano_key)
    if not item:
        raise HTTPException(status_code=400, detail="Plano inválido")
    item = dict(item)
    if valor_override is not None:
        item["valor"] = float(valor_override)
    if dias_override is not None:
        item["dias"] = int(dias_override)
    return item

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

def qrcode_base64(valor: str) -> str:
    qr = qrcode.make(valor)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"

def buscar_aluno_por_id(db, aluno_id: int) -> Optional[AlunoDB]:
    return db.query(AlunoDB).filter(AlunoDB.id == aluno_id).first()

def buscar_aluno_por_cpf(db, cpf: str) -> Optional[AlunoDB]:
    return db.query(AlunoDB).filter(AlunoDB.cpf == only_digits(cpf)).first()


def valor_base_plano_nome(db, plano_nome: Optional[str]) -> float:
    nome = (plano_nome or "Mensal").strip().lower()
    if nome == "anual":
        return ANUAL_VALOR
    if nome == "semestral":
        return SEMESTRAL_VALOR
    if nome == "promocional":
        return float(get_config(db, "promocional_valor", str(PROMOCIONAL_VALOR_PADRAO)))
    return MENSAL_VALOR


def beneficio_ativo_aluno(aluno: AlunoDB) -> bool:
    return bool(aluno.beneficio_ativo) and obter_status_por_regras(aluno) != "inativo"


def valor_cobrado_aluno(db, aluno: AlunoDB, plano_nome: Optional[str] = None) -> float:
    plano_ref = plano_nome or aluno.plano_nome
    valor_padrao = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, plano_ref)
    valor_personalizado = float(aluno.valor_personalizado or 0)
    if beneficio_ativo_aluno(aluno) and valor_personalizado > 0:
        return round(valor_personalizado, 2)

    base = float(aluno.valor_plano or 0) or valor_padrao
    desconto = float(aluno.desconto_percentual or 0)
    desconto = max(0.0, min(100.0, desconto))
    return round(base * (1 - desconto / 100.0), 2)


def desconto_percentual_real(db, aluno: AlunoDB, plano_nome: Optional[str] = None) -> float:
    plano_ref = plano_nome or aluno.plano_nome
    valor_padrao = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, plano_ref)
    valor_real = valor_cobrado_aluno(db, aluno, plano_ref)
    if valor_padrao <= 0 or valor_real >= valor_padrao:
        return float(aluno.desconto_percentual or 0)
    return round(((valor_padrao - valor_real) / valor_padrao) * 100.0, 2)


def valor_final_aluno(db, aluno: AlunoDB) -> float:
    return valor_cobrado_aluno(db, aluno, aluno.plano_nome)


def aluno_dict(db, aluno: AlunoDB) -> dict:
    status = obter_status_por_regras(aluno)
    valor_padrao = float(aluno.valor_padrao_plano or 0) or valor_base_plano_nome(db, aluno.plano_nome)
    valor_personalizado = float(aluno.valor_personalizado or 0)
    beneficio_ativo = beneficio_ativo_aluno(aluno)
    return {
        "id": aluno.id,
        "nome": aluno.nome,
        "telefone": aluno.telefone,
        "cpf": aluno.cpf,
        "email": aluno.email,
        "sexo": aluno.sexo,
        "status": status,
        "status_manual": aluno.status_manual,
        "plano_nome": aluno.plano_nome,
        "valor_plano": float(aluno.valor_plano or 0),
        "valor_padrao_plano": valor_padrao,
        "valor_personalizado": valor_personalizado if valor_personalizado > 0 else None,
        "beneficio_ativo": beneficio_ativo,
        "origem_valor": aluno.origem_valor,
        "desconto_percentual": desconto_percentual_real(db, aluno),
        "valor_final": valor_final_aluno(db, aluno),
        "vencimento": aluno.vencimento,
        "foto_url": aluno.foto_url,
        "foto_base64": aluno.foto_base64,
        "data_cadastro": aluno.data_cadastro,
        "status_cliente_raw": aluno.status_cliente_raw,
        "status_contrato_raw": aluno.status_contrato_raw,
    }

def calcular_progresso(total_entradas: int) -> dict:
    if total_entradas <= 10:
        return {
            "nivel": "cinza",
            "cor": "gray",
            "mensagem": "Ótimo começo. Cada treino conta.",
            "proxima_meta": 11,
        }
    if total_entradas <= 25:
        return {
            "nivel": "bronze",
            "cor": "bronze",
            "mensagem": "Muito bem. Sua constância já chama atenção.",
            "proxima_meta": 26,
        }
    if total_entradas <= 50:
        return {
            "nivel": "prata",
            "cor": "blue",
            "mensagem": "Excelente ritmo. Você está construindo resultado real.",
            "proxima_meta": 51,
        }
    if total_entradas <= 100:
        return {
            "nivel": "ouro",
            "cor": "gold",
            "mensagem": "Impressionante. Seu compromisso está em outro nível.",
            "proxima_meta": 101,
        }
    return {
        "nivel": "premium",
        "cor": "premium",
        "mensagem": "Você é elite. Sua disciplina virou identidade.",
        "proxima_meta": 200,
    }

def calcular_novo_vencimento(vencimento_atual: Optional[str], dias: int) -> str:
    atual = parse_date_safe(vencimento_atual)
    base = atual if atual and atual >= hoje() else hoje()
    return (base + timedelta(days=dias)).strftime("%Y-%m-%d")

def obter_link_plano(db, plano_key: str) -> Optional[str]:
    plano_key = plano_key.strip().lower()
    link_db = get_config(db, f"link_{plano_key}", "").strip()
    if link_db:
        return link_db
    defaults = {
        "mensal": PAYMENT_LINK_MENSAL,
        "semestral": PAYMENT_LINK_SEMESTRAL,
        "anual": PAYMENT_LINK_ANUAL,
        "promocional": PAYMENT_LINK_PROMOCIONAL,
    }
    return defaults.get(plano_key, "")

# ----------------------
# Root
# ----------------------
@app.get("/")
def root():
    return {"message": "API do Coliseu Fit funcionando"}

@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}

# ----------------------
# Admin
# ----------------------
@app.post("/admin/login")
def admin_login(body: AdminLoginBody):
    if body.login == ADMIN_LOGIN and body.senha == ADMIN_PASSWORD:
        return {"ok": True, "message": "Login realizado com sucesso"}
    raise HTTPException(status_code=401, detail="Login ou senha inválidos")

# ----------------------
# Config / Planos / Links
# ----------------------
@app.get("/config/planos")
def obter_config_planos():
    db = SessionLocal()
    try:
        return {
            "mensal": {"valor": MENSAL_VALOR, "dias": 30, "link": obter_link_plano(db, "mensal")},
            "semestral": {"valor": SEMESTRAL_VALOR, "dias": 180, "link": obter_link_plano(db, "semestral")},
            "anual": {"valor": ANUAL_VALOR, "dias": 365, "link": obter_link_plano(db, "anual")},
            "promocional": {
                "valor": float(get_config(db, "promocional_valor", str(PROMOCIONAL_VALOR_PADRAO))),
                "dias": int(get_config(db, "promocional_dias", str(PROMOCIONAL_DIAS_PADRAO))),
                "link": obter_link_plano(db, "promocional"),
            },
        }
    finally:
        db.close()

@app.put("/config/promocional")
def atualizar_promocional(body: PromocionalConfigBody):
    db = SessionLocal()
    try:
        set_config(db, "promocional_valor", str(body.valor))
        set_config(db, "promocional_dias", str(body.dias))
        return {"ok": True, "message": "Plano promocional atualizado"}
    finally:
        db.close()

@app.put("/config/payment-links")
def atualizar_payment_links(body: PaymentLinksBody):
    db = SessionLocal()
    try:
        if body.mensal is not None:
            set_config(db, "link_mensal", body.mensal.strip())
        if body.semestral is not None:
            set_config(db, "link_semestral", body.semestral.strip())
        if body.anual is not None:
            set_config(db, "link_anual", body.anual.strip())
        if body.promocional is not None:
            set_config(db, "link_promocional", body.promocional.strip())
        return {"ok": True, "message": "Links de pagamento atualizados"}
    finally:
        db.close()

# ----------------------
# Alunos
# ----------------------
@app.post("/alunos")
def criar_aluno(body: AlunoCreate = Body(...)):
    db = SessionLocal()
    try:
        payload_nome = (body.nome or "").strip()
        payload_telefone = (body.telefone or None)
        payload_cpf = (body.cpf or "")
        payload_email = (body.email or None)
        payload_sexo = (body.sexo or None)
        payload_plano = (body.plano_nome or None)
        payload_dias = (body.dias_plano or None)
        payload_desconto = float(body.desconto_percentual or 0)

        if not payload_nome:
            raise HTTPException(status_code=400, detail="Nome obrigatório")

        cpf_limpo = only_digits(payload_cpf)
        if not validar_cpf(cpf_limpo):
            raise HTTPException(status_code=400, detail="CPF inválido")

        if buscar_aluno_por_cpf(db, cpf_limpo):
            raise HTTPException(status_code=400, detail="CPF já cadastrado")

        plano_normalizado = None
        valor_plano = 0.0
        if payload_plano:
            try:
                plano_info = info_plano(db, payload_plano.strip().lower())
                plano_normalizado = plano_info["nome"]
                valor_plano = float(plano_info["valor"])
                if payload_dias is None:
                    payload_dias = int(plano_info["dias"])
            except Exception:
                plano_normalizado = payload_plano
                valor_plano = 0.0

        aluno = AlunoDB(
    nome=payload_nome,
    telefone=payload_telefone,
    cpf=cpf_limpo,
    email=payload_email,
    sexo=payload_sexo,
    plano_nome=plano_normalizado,
    valor_plano=valor_plano,
    vencimento=None,
    data_cadastro=agora_str(),
    status_cliente_raw="pendente",
    status_contrato_raw="aguardando_pagamento",
)
        db.add(aluno)
        db.commit()
        db.refresh(aluno)
        return {"mensagem": "Aluno criado com sucesso", "aluno": aluno_dict(db, aluno)}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/alunos")
def listar_alunos(
    status: Optional[str] = Query(default=None),
    busca: Optional[str] = Query(default=None),
):
    db = SessionLocal()
    try:
        alunos = db.query(AlunoDB).order_by(AlunoDB.nome.asc()).all()
        resultado = [aluno_dict(db, a) for a in alunos]

        if status:
            status = status.strip().lower()
            resultado = [a for a in resultado if a["status"] == status]

        if busca:
            b = busca.strip().lower()
            resultado = [
                a for a in resultado
                if b in (a["nome"] or "").lower()
                or b in (a["cpf"] or "").lower()
                or b in (a["telefone"] or "").lower()
            ]

        return resultado
    finally:
        db.close()

@app.get("/aluno/{aluno_id}")
def detalhar_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return aluno_dict(db, aluno)
    finally:
        db.close()

@app.get("/aluno/cpf/{cpf}")
def detalhar_aluno_por_cpf(cpf: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_cpf(db, cpf)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return aluno_dict(db, aluno)
    finally:
        db.close()

@app.put("/alunos/{aluno_id}")
def atualizar_aluno_admin(aluno_id: int, body: AlunoAdminUpdate):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        novo_cpf = only_digits(body.cpf)
        if not validar_cpf(novo_cpf):
            raise HTTPException(status_code=400, detail="CPF inválido")

        outro = buscar_aluno_por_cpf(db, novo_cpf)
        if outro and outro.id != aluno.id:
            raise HTTPException(status_code=400, detail="CPF já cadastrado em outro aluno")

        aluno.nome = body.nome.strip()
        aluno.telefone = (body.telefone or "").strip() or None
        aluno.cpf = novo_cpf
        aluno.email = (body.email or "").strip() or None
        aluno.sexo = (body.sexo or "").strip() or None
        if body.plano_nome is not None:
            aluno.plano_nome = body.plano_nome
        if body.valor_plano is not None:
            aluno.valor_plano = body.valor_plano
            aluno.valor_padrao_plano = body.valor_plano
            if not aluno.valor_personalizado:
                aluno.valor_personalizado = body.valor_plano
        if body.desconto_percentual is not None:
            aluno.desconto_percentual = float(body.desconto_percentual)
        if body.vencimento is not None:
            aluno.vencimento = body.vencimento
        if body.status_manual is not None:
            aluno.status_manual = body.status_manual
        aluno.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Aluno atualizado", "aluno": aluno_dict(db, aluno)}
    finally:
        db.close()


@app.put("/alunos/{aluno_id}/desconto")
def atualizar_desconto_aluno(aluno_id: int, body: DescontoBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        aluno.desconto_percentual = float(body.desconto_percentual or 0)
        valor_padrao = float(aluno.valor_padrao_plano or aluno.valor_plano or valor_base_plano_nome(db, aluno.plano_nome))
        if body.desconto_percentual and body.desconto_percentual > 0:
            aluno.valor_personalizado = round(valor_padrao * (1 - float(body.desconto_percentual)/100.0), 2)
            aluno.beneficio_ativo = True
        else:
            aluno.valor_personalizado = None
            aluno.beneficio_ativo = True
        aluno.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Desconto atualizado", "aluno": aluno_dict(db, aluno)}
    finally:
        db.close()

@app.put("/aluno/{aluno_id}/perfil")
def atualizar_aluno_self(aluno_id: int, body: AlunoSelfUpdate):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        aluno.nome = body.nome.strip()
        aluno.telefone = (body.telefone or "").strip() or None
        aluno.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Perfil atualizado", "aluno": aluno_dict(db, aluno)}
    finally:
        db.close()

@app.put("/aluno/{aluno_id}/foto")
def atualizar_foto_aluno(aluno_id: int, body: FotoAlunoBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        aluno.foto_url = body.foto_url
        aluno.foto_base64 = body.foto_base64
        aluno.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(aluno)
        return {"ok": True, "message": "Foto atualizada", "aluno": aluno_dict(db, aluno)}
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
        return {"ok": True, "message": "Aluno excluído"}
    finally:
        db.close()

# ----------------------
# Pagamentos
# ----------------------
@app.post("/alunos/{aluno_id}/pagamentos")
def registrar_pagamento(aluno_id: int, body: PagamentoBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        plano = info_plano(db, body.plano, body.valor, body.dias)
        valor_final = valor_cobrado_aluno(db, aluno, plano["nome"])
        vencimento_anterior = aluno.vencimento
        novo_vencimento = calcular_novo_vencimento(aluno.vencimento, plano["dias"])

        aluno.plano_nome = plano["nome"]
        aluno.valor_padrao_plano = valor_base_plano_nome(db, plano["nome"])
        if not beneficio_ativo_aluno(aluno):
            aluno.valor_personalizado = None
        aluno.valor_plano = valor_cobrado_aluno(db, aluno, plano["nome"])
        aluno.vencimento = novo_vencimento
        aluno.status_manual = "em_dia"
        aluno.updated_at = datetime.utcnow()

        pagamento = PagamentoDB(
            aluno_id=aluno.id,
            plano_nome=plano["nome"],
            valor=valor_final,
            dias=int(plano["dias"]),
            status="pago",
            origem=body.origem,
            data_pagamento=datetime.utcnow(),
            vencimento_anterior=vencimento_anterior,
            novo_vencimento=novo_vencimento,
        )
        db.add(pagamento)
        db.commit()
        db.refresh(aluno)

        return {
            "ok": True,
            "message": "Pagamento registrado com sucesso",
            "aluno": aluno_dict(db, aluno),
        }
    finally:
        db.close()

@app.get("/alunos/{aluno_id}/pagamentos")
def listar_pagamentos_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        pagamentos = (
            db.query(PagamentoDB)
            .filter(PagamentoDB.aluno_id == aluno_id)
            .order_by(PagamentoDB.data_pagamento.desc())
            .all()
        )
        return [
            {
                "id": p.id,
                "plano_nome": p.plano_nome,
                "valor": p.valor,
                "dias": p.dias,
                "status": p.status,
                "origem": p.origem,
                "data_pagamento": p.data_pagamento.isoformat(),
                "novo_vencimento": p.novo_vencimento,
            }
            for p in pagamentos
        ]
    finally:
        db.close()

@app.get("/pagamentos/link/{aluno_id}")
def obter_link_pagamento(aluno_id: int, plano: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        plano_info = info_plano(db, plano)
        link = obter_link_plano(db, plano)
        valor_final = valor_cobrado_aluno(db, aluno, plano_info["nome"])
        return {
            "ok": True,
            "plano": plano_info["nome"],
            "valor": valor_final,
            "dias": plano_info["dias"],
            "handle": INFINITEPAY_HANDLE,
            "link": link,
            "message": "Link retornado com sucesso",
        }
    finally:
        db.close()



@app.get("/aluno/{aluno_id}/link-pagamento")
def obter_link_pagamento_aluno(aluno_id: int, plano: Optional[str] = None):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        plano_key = (plano or (aluno.plano_nome or "Mensal")).strip().lower()
        if plano_key == "mensal":
            plano_key = "mensal"
        elif plano_key == "semestral":
            plano_key = "semestral"
        elif plano_key == "anual":
            plano_key = "anual"
        else:
            plano_key = "promocional"
        plano_info = info_plano(db, plano_key)
        link = obter_link_plano(db, plano_key)
        valor_final = valor_cobrado_aluno(db, aluno, plano_info["nome"])
        return {
            "ok": True,
            "plano": plano_info["nome"],
            "valor": valor_final,
            "dias": plano_info["dias"],
            "handle": INFINITEPAY_HANDLE,
            "link": link,
            "message": "Link retornado com sucesso",
        }
    finally:
        db.close()

# ----------------------
# Avisos
# ----------------------
@app.post("/avisos")
def criar_aviso(body: AvisoCreate = Body(...)):
    db = SessionLocal()
    try:
        aviso = AvisoDB(
            titulo=body.titulo.strip(),
            mensagem=body.mensagem.strip(),
            imagem_base64=(body.imagem_base64 or body.image_base64),
        )
        db.add(aviso)
        db.commit()
        db.refresh(aviso)
        return {"ok": True, "message": "Aviso criado com sucesso", "aviso_id": aviso.id}
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
    finally:
        db.close()

@app.get("/avisos")
def listar_avisos():
    db = SessionLocal()
    try:
        avisos = db.query(AvisoDB).order_by(AvisoDB.data.desc()).all()
        return [
            {
                "id": a.id,
                "titulo": a.titulo,
                "mensagem": a.mensagem,
                "imagem_base64": a.imagem_base64,
                "data": a.data.isoformat(),
            }
            for a in avisos
        ]
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
        return {"ok": True, "message": "Aviso excluído"}
    finally:
        db.close()

@app.post("/avisos/{aviso_id}/ler")
def marcar_aviso_lido(aviso_id: int, body: AvisoLidoBody):
    db = SessionLocal()
    try:
        item = (
            db.query(AvisoLeituraDB)
            .filter(AvisoLeituraDB.aviso_id == aviso_id, AvisoLeituraDB.aluno_id == body.aluno_id)
            .first()
        )
        if not item:
            item = AvisoLeituraDB(aviso_id=aviso_id, aluno_id=body.aluno_id, lido=True)
            db.add(item)
        db.commit()
        return {"ok": True}
    finally:
        db.close()

@app.get("/alunos/{aluno_id}/avisos/nao-lidos")
def avisos_nao_lidos(aluno_id: int):
    db = SessionLocal()
    try:
        total = db.query(AvisoDB).count()
        lidos = (
            db.query(AvisoLeituraDB)
            .filter(AvisoLeituraDB.aluno_id == aluno_id, AvisoLeituraDB.lido == True)
            .count()
        )
        return {"nao_lidos": max(total - lidos, 0)}
    finally:
        db.close()

# ----------------------
# Treinos
# ----------------------
@app.post("/treinos")
def criar_treino(body: TreinoCreate):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, body.aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        treino = TreinoDB(
            aluno_id=body.aluno_id,
            categoria=body.categoria,
            titulo=body.titulo.strip(),
            descricao=(body.descricao or "").strip() or None,
            exercicios=(body.exercicios or "").strip() or None,
            video_url=(body.video_url or "").strip() or None,
        )
        db.add(treino)
        db.commit()
        db.refresh(treino)
        return {"ok": True, "message": "Treino criado", "treino_id": treino.id}
    finally:
        db.close()

@app.get("/alunos/{aluno_id}/treinos")
def listar_treinos(aluno_id: int):
    db = SessionLocal()
    try:
        treinos = (
            db.query(TreinoDB)
            .filter(TreinoDB.aluno_id == aluno_id)
            .order_by(TreinoDB.categoria.asc(), TreinoDB.id.desc())
            .all()
        )
        return [
            {
                "id": t.id,
                "categoria": t.categoria,
                "titulo": t.titulo,
                "descricao": t.descricao,
                "exercicios": t.exercicios,
                "video_url": t.video_url,
            }
            for t in treinos
        ]
    finally:
        db.close()

@app.put("/treinos/{treino_id}")
def atualizar_treino(treino_id: int, body: TreinoCreate):
    db = SessionLocal()
    try:
        treino = db.query(TreinoDB).filter(TreinoDB.id == treino_id).first()
        if not treino:
            raise HTTPException(status_code=404, detail="Treino não encontrado")
        treino.categoria = body.categoria
        treino.titulo = body.titulo.strip()
        treino.descricao = (body.descricao or "").strip() or None
        treino.exercicios = (body.exercicios or "").strip() or None
        treino.video_url = (body.video_url or "").strip() or None
        db.commit()
        return {"ok": True, "message": "Treino atualizado"}
    finally:
        db.close()

@app.delete("/treinos/{treino_id}")
def excluir_treino(treino_id: int):
    db = SessionLocal()
    try:
        treino = db.query(TreinoDB).filter(TreinoDB.id == treino_id).first()
        if not treino:
            raise HTTPException(status_code=404, detail="Treino não encontrado")
        db.delete(treino)
        db.commit()
        return {"ok": True, "message": "Treino excluído"}
    finally:
        db.close()

# ----------------------
# Acesso / Catraca
# ----------------------
@app.get("/catraca/qr")
def obter_qr_catraca():
    return {"codigo": QR_CATRACA, "qr_image_base64": qrcode_base64(QR_CATRACA)}

@app.post("/entrada/{aluno_id}")
def registrar_entrada(aluno_id: int, body: EntradaBody = Body(...)):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        status_aluno = obter_status_por_regras(aluno)
        codigo_qr = (body.codigo_qr or "").strip()

        if status_aluno != "em_dia":
            item = EntradaDB(
                aluno_id=aluno.id,
                nome=aluno.nome,
                status="bloqueado",
                motivo="pagamento pendente ou status inválido",
            )
            db.add(item)
            db.commit()
            return {
                "acesso": "bloqueado",
                "mensagem": "Pagamento pendente. Regularize sua mensalidade.",
                "ir_para_pagamento": True,
            }

        if codigo_qr != QR_CATRACA.strip():
            item = EntradaDB(
                aluno_id=aluno.id,
                nome=aluno.nome,
                status="bloqueado",
                motivo="qr inválido",
            )
            db.add(item)
            db.commit()
            return {
                "acesso": "bloqueado",
                "mensagem": "QR da catraca inválido.",
                "ir_para_pagamento": False,
            }

        item = EntradaDB(
            aluno_id=aluno.id,
            nome=aluno.nome,
            status="liberado",
            motivo="entrada autorizada",
        )
        db.add(item)
        db.commit()

        total_entradas = (
            db.query(EntradaDB)
            .filter(EntradaDB.aluno_id == aluno.id, EntradaDB.status == "liberado")
            .count()
        )

        return {
            "acesso": "liberado",
            "mensagem": "Acesso liberado. Bom treino!",
            "total_entradas": total_entradas,
            "progresso": calcular_progresso(total_entradas),
        }
    finally:
        db.close()

@app.get("/entradas")
def listar_entradas():
    db = SessionLocal()
    try:
        entradas = db.query(EntradaDB).order_by(EntradaDB.data_entrada.desc()).all()
        return [
            {
                "id": e.id,
                "aluno_id": e.aluno_id,
                "nome": e.nome,
                "status": e.status,
                "motivo": e.motivo,
                "data_entrada": e.data_entrada.isoformat(),
            }
            for e in entradas
        ]
    finally:
        db.close()

# ----------------------
# Relatórios
# ----------------------
@app.get("/relatorio/resumo")
def relatorio_resumo():
    db = SessionLocal()
    try:
        alunos = db.query(AlunoDB).all()
        lista = [aluno_dict(db, a) for a in alunos]

        em_dia = [a for a in lista if a["status"] == "em_dia"]
        atrasados = [a for a in lista if a["status"] == "atrasado"]
        inativos = [a for a in lista if a["status"] == "inativo"]
        pendentes = [a for a in lista if a["status"] == "pendente"]

        potencial_atrasados = sum(float(a.get("valor_plano") or 0) for a in atrasados)
        faturamento_real = sum(float(a.get("valor_plano") or 0) for a in em_dia)

        return {
            "total_alunos": len(lista),
            "em_dia": len(em_dia),
            "atrasados": len(atrasados),
            "inativos": len(inativos),
            "pendentes": len(pendentes),
            "faturamento_real": faturamento_real,
            "potencial_atrasados": potencial_atrasados,
        }
    finally:
        db.close()

@app.get("/relatorio/texto/{tipo}")
def relatorio_texto(tipo: Literal["ativos", "atrasados", "inativos"]):
    db = SessionLocal()
    try:
        alunos = [aluno_dict(db, a) for a in db.query(AlunoDB).order_by(AlunoDB.nome.asc()).all()]
        mapa = {
            "ativos": "em_dia",
            "atrasados": "atrasado",
            "inativos": "inativo",
        }
        status_alvo = mapa[tipo]
        filtrados = [a for a in alunos if a["status"] == status_alvo]

        linhas = [f"Relatório ColiseuFit - {tipo.upper()}", f"Gerado em: {agora_str()}", ""]
        for idx, a in enumerate(filtrados, start=1):
            linhas.append(
                f"{idx}. {a['nome']} | CPF: {a['cpf']} | Telefone: {a['telefone'] or '-'} | "
                f"Plano: {a['plano_nome'] or '-'} | Vencimento: {a['vencimento'] or '-'}"
            )
        if not filtrados:
            linhas.append("Nenhum aluno encontrado.")
        return PlainTextResponse("\n".join(linhas), media_type="text/plain; charset=utf-8")
    finally:
        db.close()


class PagamentoLinkBody(BaseModel):
    aluno_id: int
    plano: Optional[str] = None

@app.post("/pagamentos/link")
def criar_link_pagamento(body: PagamentoLinkBody):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, body.aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        plano_key = (body.plano or aluno.plano_nome or "mensal").strip().lower()
        mapa = {
            "mensal": "mensal",
            "semestral": "semestral",
            "anual": "anual",
            "promocional": "promocional",
        }
        plano_key = mapa.get(plano_key, "mensal")
        link = obter_link_plano(db, plano_key)

        if not link:
            # fallback para handle direto
            link = f"https://link.infinitepay.io/{INFINITEPAY_HANDLE}"

        return {
            "ok": True,
            "url": link,
            "checkout_url": link,
            "plano": plano_key,
            "aluno_id": aluno.id,
        }
    finally:
        db.close()

@app.put("/pagar/{aluno_id}")
def registrar_pagamento_alias(aluno_id: int, body: PagamentoBody):
    return registrar_pagamento(aluno_id, body)

@app.get("/aluno/{aluno_id}/treinos")
def listar_treinos_alias(aluno_id: int):
    return listar_treinos(aluno_id)

@app.put("/alunos/{aluno_id}/foto")
def atualizar_foto_aluno_alias(aluno_id: int, body: FotoAlunoBody):
    return atualizar_foto_aluno(aluno_id, body)

@app.put("/config/planos/promocional")
def atualizar_promocional_alias(valor: float = Query(...), dias: int = Query(PROMOCIONAL_DIAS_PADRAO)):
    return atualizar_promocional(PromocionalConfigBody(valor=valor, dias=dias))

@app.get("/relatorios/txt")
def relatorio_texto_completo():
    db = SessionLocal()
    try:
        alunos = [aluno_dict(db, a) for a in db.query(AlunoDB).order_by(AlunoDB.nome.asc()).all()]
        pagamentos = db.query(PagamentoDB).order_by(PagamentoDB.data_pagamento.desc()).all()

        em_dia = [a for a in alunos if a["status"] == "em_dia"]
        atrasados = [a for a in alunos if a["status"] == "atrasado"]
        inativos = [a for a in alunos if a["status"] == "inativo"]
        pendentes = [a for a in alunos if a["status"] == "pendente"]

        potencial = sum(float(a.get("valor_final") or a.get("valor_plano") or 0) for a in atrasados)

        linhas = []
        linhas.append("COLISEUFIT - RELATÓRIO GERAL")
        linhas.append("")
        linhas.append(f"Total de alunos: {len(alunos)}")
        linhas.append(f"Em dia: {len(em_dia)}")
        linhas.append(f"Atrasados: {len(atrasados)}")
        linhas.append(f"Inativos: {len(inativos)}")
        linhas.append(f"Pendentes: {len(pendentes)}")
        linhas.append(f"Potencial de ganho (somente atrasados): R$ {potencial:.2f}")
        linhas.append("")

        def bloco(titulo, lista):
            linhas.append(f"=== {titulo} ({len(lista)}) ===")
            if not lista:
                linhas.append("Nenhum registro.")
            else:
                for a in lista:
                    linhas.append(
                        f"{a['nome']} | CPF: {a['cpf']} | Telefone: {a.get('telefone') or '-'} | "
                        f"Plano: {a.get('plano_nome') or '-'} | Vencimento: {a.get('vencimento') or '-'}"
                    )
            linhas.append("")

        bloco("EM DIA", em_dia)
        bloco("ATRASADOS", atrasados)
        bloco("INATIVOS", inativos)
        bloco("PENDENTES", pendentes)

        linhas.append(f"=== PAGAMENTOS REGISTRADOS ({len(pagamentos)}) ===")
        if not pagamentos:
            linhas.append("Nenhum pagamento registrado.")
        else:
            for p in pagamentos[:300]:
                nome = p.aluno.nome if getattr(p, "aluno", None) else str(p.aluno_id)
                linhas.append(
                    f"{nome} | Plano: {p.plano_nome} | Valor: R$ {p.valor:.2f} | "
                    f"Data: {p.data_pagamento.strftime('%Y-%m-%d %H:%M')} | Novo vencimento: {p.novo_vencimento or '-'}"
                )

        return PlainTextResponse("\n".join(linhas), media_type="text/plain; charset=utf-8")
    finally:
        db.close()


# ----------------------
# Compatibilidade com Flutter antigo/aprovado
# ----------------------
@app.get("/aluno/login")
def aluno_login(cpf: str):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_cpf(db, cpf)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        nao_lidos = db.query(AvisoLidoDB).filter(AvisoLidoDB.aluno_id == aluno.id).count()
        total_avisos = db.query(AvisoDB).count()
        return {
            "ok": True,
            "aluno": aluno_dict(db, aluno),
            "avisos_nao_lidos": max(total_avisos - nao_lidos, 0),
        }
    finally:
        db.close()

@app.get("/relatorio/planos")
def relatorio_planos():
    db = SessionLocal()
    try:
        alunos = [aluno_dict(db, a) for a in db.query(AlunoDB).all()]
        nomes = ["Mensal", "Semestral", "Anual", "Promocional"]
        contagem = {n: 0 for n in nomes}
        for a in alunos:
            plano = (a.get("plano_nome") or "").strip().title()
            if plano in contagem:
                contagem[plano] += 1
        return contagem
    finally:
        db.close()

@app.get("/relatorio/vendas")
def relatorio_vendas(periodo: str = "mes"):
    db = SessionLocal()
    try:
        pagamentos = db.query(PagamentoDB).order_by(PagamentoDB.data_pagamento.desc()).all()
        total = sum(float(p.valor or 0) for p in pagamentos)
        quantidade = len(pagamentos)
        return {
            "periodo": periodo,
            "total": total,
            "quantidade": quantidade,
        }
    finally:
        db.close()

@app.get("/historico")
def historico_alias():
    return listar_entradas()

@app.delete("/avisos/{aviso_id}")
def excluir_aviso(aviso_id: int):
    db = SessionLocal()
    try:
        aviso = db.query(AvisoDB).filter(AvisoDB.id == aviso_id).first()
        if not aviso:
            raise HTTPException(status_code=404, detail="Aviso não encontrado")
        db.delete(aviso)
        db.commit()
        return {"ok": True, "message": "Aviso excluído"}
    finally:
        db.close()

@app.get("/aluno/{aluno_id}/avisos")
def avisos_aluno(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        avisos = db.query(AvisoDB).order_by(AvisoDB.data.desc()).all()
        lidos_ids = {
            item.aviso_id for item in db.query(AvisoLidoDB).filter(AvisoLidoDB.aluno_id == aluno_id).all()
        }
        return {
            "avisos": [
                {
                    "id": a.id,
                    "titulo": a.titulo,
                    "mensagem": a.mensagem,
                    "imagem_base64": a.imagem_base64,
                    "data": a.data.isoformat(),
                    "lido": a.id in lidos_ids,
                }
                for a in avisos
            ],
            "nao_lidos": sum(1 for a in avisos if a.id not in lidos_ids),
        }
    finally:
        db.close()

@app.post("/aluno/{aluno_id}/avisos/{aviso_id}/ler")
def marcar_aviso_lido_compat(aluno_id: int, aviso_id: int):
    db = SessionLocal()
    try:
        existe = (
            db.query(AvisoLidoDB)
            .filter(AvisoLidoDB.aluno_id == aluno_id, AvisoLidoDB.aviso_id == aviso_id)
            .first()
        )
        if not existe:
            db.add(AvisoLidoDB(aluno_id=aluno_id, aviso_id=aviso_id))
            db.commit()
        return {"ok": True}
    finally:
        db.close()

@app.get("/aluno/{aluno_id}/pagamentos")
def pagamentos_aluno_compat(aluno_id: int):
    return listar_pagamentos_aluno(aluno_id)

@app.get("/aluno/{aluno_id}/progresso")
def progresso_aluno_compat(aluno_id: int):
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, aluno_id)
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        total = (
            db.query(EntradaDB)
            .filter(EntradaDB.aluno_id == aluno_id, EntradaDB.status == "liberado")
            .count()
        )
        return calcular_progresso(total)
    finally:
        db.close()

@app.put("/aluno/{aluno_id}/regularizar")
def regularizar_aluno_compat(aluno_id: int, dias: int = Query(...), valor: float = Query(...)):
    plano = "mensal"
    if dias >= 365:
        plano = "anual"
    elif dias >= 180:
        plano = "semestral"
    elif dias >= 30 and valor < MENSAL_VALOR:
        plano = "promocional"
    elif dias >= 30:
        plano = "mensal"
    return registrar_pagamento(aluno_id, PagamentoBody(plano=plano, valor=valor, dias=dias, origem="manual"))

@app.get("/admin/treinos")
def listar_treinos_admin(aluno_id: Optional[int] = Query(default=None)):
    db = SessionLocal()
    try:
        q = db.query(TreinoDB)
        if aluno_id:
            q = q.filter(TreinoDB.aluno_id == aluno_id)
        treinos = q.order_by(TreinoDB.id.desc()).all()
        return [
            {
                "id": t.id,
                "aluno_id": t.aluno_id,
                "categoria": t.categoria,
                "titulo": t.titulo,
                "descricao": t.descricao,
                "exercicios": t.exercicios,
                "video_url": t.video_url,
            }
            for t in treinos
        ]
    finally:
        db.close()

class TreinoCompatCreate(BaseModel):
    aluno_id: int
    codigo: Optional[str] = None
    categoria: Optional[str] = None
    titulo: str
    descricao: Optional[str] = None
    exercicios: Optional[list[str]] = None
    video_url: Optional[str] = None
    ordem: Optional[int] = None

@app.post("/treinos/compat")
def salvar_treino_compat(body: TreinoCompatCreate):
    categoria = (body.categoria or body.codigo or "A").strip().upper()
    if categoria not in ["A", "B", "C", "D", "E"]:
        categoria = "A"
    descricao = body.descricao
    if not descricao and body.exercicios:
        descricao = "\n".join(body.exercicios)
    return criar_treino(TreinoCreate(
        aluno_id=body.aluno_id,
        categoria=categoria,
        titulo=body.titulo,
        descricao=descricao,
        exercicios=descricao,
        video_url=body.video_url,
    ))

@app.post("/pagamentos/criar")
def criar_pagamento_checkout_compat(
    body: Optional[dict] = None,
    aluno_id: Optional[int] = Query(default=None),
    dias: Optional[int] = Query(default=None),
    valor: Optional[float] = Query(default=None),
    plano_nome: Optional[str] = Query(default=None),
):
    # compatível com o Flutter antigo: sempre retorna link real/stub e sem marcar pago sozinho
    payload = body or {}
    aluno_id = aluno_id or payload.get("aluno_id")
    dias = dias or payload.get("dias")
    valor = valor or payload.get("valor")
    plano_nome = plano_nome or payload.get("plano_nome")
    if not aluno_id:
        raise HTTPException(status_code=400, detail="aluno_id obrigatório")
    db = SessionLocal()
    try:
        aluno = buscar_aluno_por_id(db, int(aluno_id))
        if not aluno:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        plano_key = "mensal"
        if plano_nome:
            txt = str(plano_nome).lower()
            if "promo" in txt:
                plano_key = "promocional"
            elif "anual" in txt:
                plano_key = "anual"
            elif "semes" in txt:
                plano_key = "semestral"
            else:
                plano_key = "mensal"
        elif dias:
            plano_key = "anual" if int(dias) >= 365 else "semestral" if int(dias) >= 180 else "mensal"
        link = obter_link_plano(db, plano_key) or f"https://link.infinitepay.io/{INFINITEPAY_HANDLE}"
        return {
            "ok": True,
            "modo": "link_real",
            "checkout_url": link,
            "pagamento": {"id": 0},
        }
    finally:
        db.close()

@app.post("/pagamentos/{pagamento_id}/aprovar-demo")
def aprovar_pagamento_demo(pagamento_id: int):
    return {"ok": True, "mensagem": "Modo demo desativado. Use o link real para pagar."}
# deploy render atualizado