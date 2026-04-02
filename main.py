from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import Optional
import qrcode
import os

app = FastAPI(title="Academia API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CONFIG
# =========================
QR_CATRACA = "CATRACA_ACADEMIA_01"

PLANOS = {
    30: {"nome": "Mensal", "valor": 100},
    90: {"nome": "Trimestral", "valor": 250},
    180: {"nome": "Semestral", "valor": 450},
    365: {"nome": "Anual", "valor": 800},
}

# =========================
# DADOS EM MEMÓRIA
# =========================
alunos = []
historico_pagamentos = []
historico_entradas = []
avisos = []

# =========================
# HELPERS
# =========================
def agora_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def hoje():
    return datetime.now()

def obter_status_aluno(aluno: dict) -> str:
    vencimento = datetime.strptime(aluno["vencimento"], "%Y-%m-%d")
    return "em dia" if hoje() <= vencimento else "atrasado"

def buscar_aluno(aluno_id: int) -> Optional[dict]:
    for aluno in alunos:
        if aluno["id"] == aluno_id:
            return aluno
    return None

def gerar_qr_aluno(aluno_id: int):
    qr = qrcode.make(f"aluno:{aluno_id}")
    qr.save(f"qrcode_{aluno_id}.png")

def remover_qr_aluno(aluno_id: int):
    arquivo = f"qrcode_{aluno_id}.png"
    if os.path.exists(arquivo):
        os.remove(arquivo)

def info_plano_por_dias(dias: int):
    return PLANOS.get(dias, {"nome": f"{dias} dias", "valor": 0})

def listar_alunos_com_status():
    resultado = []
    for aluno in alunos:
        status = obter_status_aluno(aluno)
        resultado.append({**aluno, "status": status})
    return resultado

def filtrar_alunos(status: Optional[str] = None, plano: Optional[str] = None):
    lista = listar_alunos_com_status()

    if status:
        lista = [
            a for a in lista
            if (a["status"] or "").lower() == status.lower()
        ]

    if plano:
        lista = [
            a for a in lista
            if (a.get("plano_atual") or "").lower() == plano.lower()
        ]

    return lista

def calcular_resumo():
    lista = listar_alunos_com_status()

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

def pagamentos_por_periodo(periodo: str):
    agora = datetime.now()

    if periodo == "semana":
        inicio = agora - timedelta(days=7)
    elif periodo == "quinzena":
        inicio = agora - timedelta(days=15)
    elif periodo == "mes":
        inicio = agora - timedelta(days=30)
    else:
        return historico_pagamentos

    filtrados = []
    for p in historico_pagamentos:
        data = datetime.strptime(p["data_pagamento"], "%Y-%m-%d %H:%M")
        if data >= inicio:
            filtrados.append(p)
    return filtrados

# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"message": "API da academia funcionando"}

# =========================
# ALUNOS
# =========================
@app.post("/alunos")
def criar_aluno(nome: str, telefone: str, dias_plano: int = 30):
    aluno_id = len(alunos) + 1
    plano_info = info_plano_por_dias(dias_plano)
    vencimento = hoje() + timedelta(days=dias_plano)

    aluno = {
        "id": aluno_id,
        "nome": nome,
        "telefone": telefone,
        "vencimento": vencimento.strftime("%Y-%m-%d"),
        "valor_plano": plano_info["valor"],
        "plano_atual": plano_info["nome"],
    }

    alunos.append(aluno)
    gerar_qr_aluno(aluno_id)

    return {
        "mensagem": "Aluno criado com sucesso",
        "aluno": aluno,
        "status": obter_status_aluno(aluno),
    }

@app.get("/alunos")
def listar_alunos(
    status: Optional[str] = Query(default=None),
    plano: Optional[str] = Query(default=None),
):
    return filtrar_alunos(status=status, plano=plano)

@app.get("/aluno/{aluno_id}")
def detalhar_aluno(aluno_id: int):
    aluno = buscar_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    return {**aluno, "status": obter_status_aluno(aluno)}

@app.put("/alunos/{aluno_id}")
def editar_aluno(aluno_id: int, nome: str, telefone: str):
    aluno = buscar_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    aluno["nome"] = nome
    aluno["telefone"] = telefone

    return {
        "mensagem": "Aluno atualizado com sucesso",
        "aluno": {**aluno, "status": obter_status_aluno(aluno)},
    }

@app.delete("/alunos/{aluno_id}")
def excluir_aluno(aluno_id: int):
    for i, aluno in enumerate(alunos):
        if aluno["id"] == aluno_id:
            remover_qr_aluno(aluno_id)
            alunos.pop(i)
            return {"mensagem": "Aluno excluído com sucesso"}

    raise HTTPException(status_code=404, detail="Aluno não encontrado")

# =========================
# PAGAMENTOS
# =========================
@app.put("/pagar/{aluno_id}")
def registrar_pagamento(aluno_id: int, dias: int = 30, valor: Optional[float] = None):
    aluno = buscar_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    plano_info = info_plano_por_dias(dias)
    valor_final = valor if valor is not None else plano_info["valor"]

    vencimento_atual = datetime.strptime(aluno["vencimento"], "%Y-%m-%d")
    base = vencimento_atual if vencimento_atual >= hoje() else hoje()
    novo_vencimento = base + timedelta(days=dias)

    aluno["vencimento"] = novo_vencimento.strftime("%Y-%m-%d")
    aluno["plano_atual"] = plano_info["nome"]
    aluno["valor_plano"] = valor_final

    pagamento = {
        "id": len(historico_pagamentos) + 1,
        "aluno_id": aluno["id"],
        "nome": aluno["nome"],
        "plano": aluno["plano_atual"],
        "valor": valor_final,
        "data_pagamento": agora_str(),
        "origem": "manual",
    }
    historico_pagamentos.append(pagamento)

    return {
        "mensagem": "Pagamento registrado com sucesso",
        "aluno": {**aluno, "status": obter_status_aluno(aluno)},
        "pagamento": pagamento,
    }

@app.get("/historico")
def listar_historico():
    return historico_pagamentos

@app.get("/historico/filtro")
def historico_filtrado(periodo: str = "mes"):
    lista = pagamentos_por_periodo(periodo)
    total = sum(float(p["valor"]) for p in lista)

    return {
        "periodo": periodo,
        "total_registros": len(lista),
        "faturamento": total,
        "pagamentos": lista,
    }

# =========================
# ACESSO / CATRACA
# =========================
@app.get("/validar/{aluno_id}")
def validar_acesso(aluno_id: int):
    aluno = buscar_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    status = obter_status_aluno(aluno)
    return {"acesso": "liberado" if status == "em dia" else "bloqueado"}

@app.post("/entrada/{aluno_id}")
def registrar_entrada(aluno_id: int, codigo_qr: str):
    aluno = buscar_aluno(aluno_id)
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")

    status = obter_status_aluno(aluno)

    if status != "em dia":
        item = {
            "id": len(historico_entradas) + 1,
            "aluno_id": aluno["id"],
            "nome": aluno["nome"],
            "status": "bloqueado",
            "motivo": "pagamento pendente",
            "data_entrada": agora_str(),
        }
        historico_entradas.append(item)
        return {
            "acesso": "bloqueado",
            "mensagem": "Pagamento pendente. Regularize sua mensalidade.",
        }

    if codigo_qr != QR_CATRACA:
        item = {
            "id": len(historico_entradas) + 1,
            "aluno_id": aluno["id"],
            "nome": aluno["nome"],
            "status": "bloqueado",
            "motivo": "qr inválido",
            "data_entrada": agora_str(),
        }
        historico_entradas.append(item)
        return {
            "acesso": "bloqueado",
            "mensagem": "QR da catraca inválido.",
        }

    item = {
        "id": len(historico_entradas) + 1,
        "aluno_id": aluno["id"],
        "nome": aluno["nome"],
        "status": "liberado",
        "motivo": "entrada autorizada",
        "data_entrada": agora_str(),
    }
    historico_entradas.append(item)

    return {
        "acesso": "liberado",
        "mensagem": "Acesso liberado. Bom treino!",
    }

@app.get("/entradas")
def listar_entradas():
    return historico_entradas

@app.get("/catraca/qr")
def obter_qr_catraca():
    return {"codigo": QR_CATRACA}

# =========================
# AVISOS
# =========================
@app.post("/avisos")
def criar_aviso(titulo: str, mensagem: str, image_url: Optional[str] = None):
    aviso = {
        "id": len(avisos) + 1,
        "titulo": titulo,
        "mensagem": mensagem,
        "image_url": image_url,
        "data": agora_str(),
    }
    avisos.append(aviso)
    return {"mensagem": "Aviso criado com sucesso", "aviso": aviso}

@app.get("/avisos")
def listar_avisos():
    return list(reversed(avisos))

@app.delete("/avisos/{aviso_id}")
def excluir_aviso(aviso_id: int):
    for i, aviso in enumerate(avisos):
        if aviso["id"] == aviso_id:
            avisos.pop(i)
            return {"mensagem": "Aviso excluído com sucesso"}

    raise HTTPException(status_code=404, detail="Aviso não encontrado")

# =========================
# RELATÓRIOS
# =========================
@app.get("/relatorio/resumo")
def relatorio_resumo():
    return calcular_resumo()

@app.get("/relatorio/planos")
def relatorio_planos():
    lista = listar_alunos_com_status()

    resumo = {
        "Mensal": 0,
        "Trimestral": 0,
        "Semestral": 0,
        "Anual": 0,
    }

    for aluno in lista:
        plano = aluno.get("plano_atual", "")
        if plano in resumo:
            resumo[plano] += 1

    return resumo

@app.get("/relatorio/alunos")
def relatorio_alunos(
    status: Optional[str] = Query(default=None),
    plano: Optional[str] = Query(default=None),
):
    lista = filtrar_alunos(status=status, plano=plano)
    return {
        "total": len(lista),
        "alunos": lista,
    }

@app.get("/relatorio/vendas")
def relatorio_vendas(periodo: str = "mes"):
    pagamentos = pagamentos_por_periodo(periodo)
    total = sum(float(p["valor"]) for p in pagamentos)

    resumo = calcular_resumo()

    return {
        "periodo": periodo,
        "faturamento_obtido": total,
        "faturamento_real_atual": resumo["faturamento_real"],
        "faturamento_potencial": resumo["faturamento_potencial"],
        "inadimplencia_valor": resumo["inadimplencia_valor"],
        "pagamentos": pagamentos,
    }