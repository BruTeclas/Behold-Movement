#!/usr/bin/env python3
"""Gera n8n/behold-inscricao.json, o workflow de inscrições do Behold Movement.

Fluxo:
  site -> webhook -> valida e padroniza -> planilha (adiciona ou atualiza pelo
  telefone) -> responde ao site -> e-mail de boas-vindas (Gmail) -> espera
  alguns segundos -> Chatwoot (contato + conversa com a mensagem de WhatsApp)
  -> grava na planilha o status de cada envio.

Uso: python3 scripts/build-n8n.py
"""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "n8n" / "behold-inscricao.json"

PLANILHA_ID = "1q1x8UUi4KOTB6ES8HToqCWhA9uCCkvchnFlU1ZWn8jE"
PLANILHA_URL = f"https://docs.google.com/spreadsheets/d/{PLANILHA_ID}/edit"
SITE_ORIGENS = "https://beholdmovement.com.br,https://www.beholdmovement.com.br"


def nid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "behold-n8n/" + name))


# ---------------------------------------------------------------- JS dos nós

JS_VALIDAR = r"""
// Lê o formulário do site, padroniza os campos e diz se a inscrição é válida.
const cfg = $('Configurações').first().json;
const b = $('Inscrição no site').first().json.body || {};

const limpa = (v) => String(v ?? '').trim().replace(/\s+/g, ' ');
const MINUSCULAS = ['da', 'de', 'do', 'das', 'dos', 'e'];
const capitaliza = (s) => limpa(s).toLowerCase().split(' ')
  .map((p, i) => (i > 0 && MINUSCULAS.includes(p)) ? p : p.charAt(0).toUpperCase() + p.slice(1))
  .join(' ');

let digitos = limpa(b.telefone_e164 || b.telefone).replace(/\D/g, '');
if (digitos.startsWith('55') && digitos.length >= 12) digitos = digitos.slice(2);

const MINISTERIOS = ['Evangelizando', 'Mídia', 'Suprimento', 'Ação social', 'Intercessão'];
const UFS = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG', 'PA', 'PB', 'PR',
  'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'];

const cepDigitos = limpa(b.cep).replace(/\D/g, '');
const rua = limpa(b.endereco);
const numero = limpa(b.numero);

const dados = {
  nome: capitaliza(b.nome),
  email: limpa(b.email).toLowerCase(),
  cep: cepDigitos.length === 8 ? cepDigitos.slice(0, 5) + '-' + cepDigitos.slice(5) : '',
  rua,
  numero,
  endereco: [rua, numero].filter(Boolean).join(', '),
  bairro: capitaliza(b.bairro),
  cidade: capitaliza(b.cidade),
  uf: limpa(b.uf).toUpperCase(),
  igreja: limpa(b.igreja),
  ministerio: limpa(b.ministerio),
  consentimento: limpa(b.consentimento) === 'sim' ? 'sim' : 'não',
};

const erros = [];
if (dados.nome.length < 3) erros.push('nome');
if (!(digitos.length === 11 && digitos.charAt(2) === '9')) erros.push('telefone');
if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(dados.email)) erros.push('email');
if (cepDigitos && cepDigitos.length !== 8) erros.push('cep');
for (const campo of ['rua', 'numero', 'bairro', 'cidade', 'igreja']) {
  if (!dados[campo]) erros.push(campo);
}
if (!UFS.includes(dados.uf)) erros.push('uf');
if (!MINISTERIOS.includes(dados.ministerio)) erros.push('ministerio');
if (dados.consentimento !== 'sim') erros.push('consentimento');

// Campo escondido "site": pessoas não veem, robôs preenchem.
const bot = limpa(b.site) !== '';

const agora = DateTime.now().setZone('America/Sao_Paulo');
return [{
  json: {
    valido: !bot && erros.length === 0,
    bot,
    erros,
    id: 'BHD-' + agora.toFormat('yyMMdd') + '-' + Math.random().toString(36).slice(2, 6).toUpperCase(),
    data_hora: agora.toFormat('yyyy-MM-dd HH:mm:ss'),
    ...dados,
    primeiro_nome: dados.nome.split(' ')[0] || '',
    telefone_e164: '+55' + digitos,
    ...cfg,
  },
}];
""".strip()

JS_MENSAGENS = r"""
// Monta o e-mail (HTML) e a mensagem de WhatsApp a partir da inscrição.
const d = $('Validar e padronizar').first().json;

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const etiqueta = 'frente-' + d.ministerio.normalize('NFD').replace(/[̀-ͯ]/g, '')
  .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

// ---------- WhatsApp
const linhas = [
  `Olá, ${d.primeiro_nome}!`,
  '',
  `Aqui é do *Behold Movement*. Recebemos sua inscrição para servir na frente de *${d.ministerio}*. Que alegria ter você com a gente!`,
  '',
  'Entre no grupo do movimento para receber as notícias e as orientações do Dia 31:',
  d.link_grupo,
];
if (d.treinamento_data) {
  linhas.push('', `*Treinamento:* ${d.treinamento_data}, às ${d.treinamento_hora}, ${d.treinamento_local}.`);
}
linhas.push(
  '',
  'Salve este número nos seus contatos para não perder nenhuma mensagem. Se tiver dúvida, é só responder aqui.',
  '',
  '_Contemple Cristo e faça Cristo ser contemplado._',
);

// ---------- E-mail
const AZUL = '#1f5bf2', TINTA = '#16171c', PAPEL = '#eceae5', CINZA = '#5d616c';
const DISPLAY = "Impact, 'Arial Narrow Bold', 'Arial Narrow', Arial, sans-serif";
const TEXTO = 'Arial, Helvetica, sans-serif';
const MONO = "'Courier New', Courier, monospace";

const agenda = [
  ['12h00', 'Encontro no Arena'],
  ['12h00 às 14h00', 'Evangelismo'],
  ['14h00', 'Retorno ao ponto de encontro'],
  ['14h30', 'Almoço na ASAFE'],
  ['16h00', 'Intercessão e oração'],
  ['17h00', 'Preparação final'],
  ['18h00', 'Culto Evangelístico'],
].map(([h, o]) => `
  <tr>
    <td width="150" style="width:150px;padding:10px 16px 10px 0;border-top:1px solid #d6d3cc;font-family:${DISPLAY};font-size:18px;color:${AZUL};white-space:nowrap;vertical-align:top;">${h}</td>
    <td style="padding:10px 0;border-top:1px solid #d6d3cc;font-family:${TEXTO};font-size:16px;color:${TINTA};">${o}</td>
  </tr>`).join('');


const blocoTreino = d.treinamento_data ? `
  <tr><td style="padding:0 32px 28px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:2px solid ${AZUL};border-radius:6px;">
      <tr><td style="padding:16px 18px;font-family:${TEXTO};font-size:15px;line-height:1.5;color:${TINTA};">
        <strong>Treinamento:</strong> ${esc(d.treinamento_data)}, às ${esc(d.treinamento_hora)}, ${esc(d.treinamento_local)}.
      </td></tr>
    </table>
  </td></tr>` : '';

const html = `<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Behold Movement</title></head>
<body style="margin:0;padding:0;background:${PAPEL};">
<div style="display:none;max-height:0;overflow:hidden;">Sua inscrição foi recebida. Entre no grupo do movimento para receber as notícias.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:${PAPEL};">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:6px;overflow:hidden;">

  <tr><td style="background:${AZUL};padding:32px 32px 28px;">
    <div style="font-family:${DISPLAY};font-size:40px;line-height:1;color:${PAPEL};letter-spacing:1px;">MOVEMENT</div>
    <div style="font-family:${DISPLAY};font-size:76px;line-height:.9;color:${TINTA};letter-spacing:1px;">BEHOLD</div>
    <div style="font-family:${MONO};font-size:13px;color:${PAPEL};margin-top:18px;">"Eis o Cordeiro de Deus, que tira o pecado do mundo." João 1:29</div>
  </td></tr>

  <tr><td style="padding:32px 32px 8px;">
    <div style="font-family:${MONO};font-weight:bold;font-size:12px;letter-spacing:3px;color:${AZUL};">INSCRIÇÃO CONFIRMADA</div>
    <h1 style="margin:10px 0 16px;font-family:${DISPLAY};font-weight:normal;font-size:34px;line-height:1.05;color:${TINTA};text-transform:uppercase;">Que bom ter você com a gente, ${esc(d.primeiro_nome)}.</h1>
    <p style="margin:0 0 16px;font-family:${TEXTO};font-size:16px;line-height:1.6;color:${TINTA};">Sua inscrição no Behold Movement foi recebida. Você escolheu servir na frente de <strong>${esc(d.ministerio)}</strong>.</p>
    <p style="margin:0 0 24px;font-family:${TEXTO};font-size:16px;line-height:1.6;color:${TINTA};">As notícias, os avisos e as orientações do movimento são compartilhados no grupo do WhatsApp. Entre agora para não perder nada.</p>
  </td></tr>

  <tr><td style="padding:0 32px 28px;">
    <a href="${esc(d.link_grupo)}" style="display:inline-block;background:${AZUL};color:#ffffff;text-decoration:none;font-family:${DISPLAY};font-size:20px;letter-spacing:1px;padding:16px 26px;border-radius:4px;text-transform:uppercase;">Entrar no grupo do WhatsApp</a>
  </td></tr>
  ${blocoTreino}

  <tr><td style="padding:8px 32px 28px;">
    <div style="font-family:${MONO};font-weight:bold;font-size:12px;letter-spacing:3px;color:${AZUL};margin-bottom:8px;">COMO SERÁ O DIA 31</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">${agenda}
    </table>
  </td></tr>

  <tr><td style="background:${TINTA};padding:28px 32px;">
    <div style="font-family:${DISPLAY};font-size:26px;line-height:1.1;color:${PAPEL};text-transform:uppercase;">"Ide por todo o mundo e pregai o evangelho <span style="color:#6e97ff;">a toda criatura."</span></div>
    <div style="font-family:${MONO};font-weight:bold;font-size:13px;color:#6e97ff;margin-top:10px;">MARCOS 16:15</div>
  </td></tr>

  <tr><td style="padding:20px 32px 28px;font-family:${TEXTO};font-size:12px;line-height:1.6;color:${CINZA};">
    <strong style="color:${TINTA};">Behold Movement</strong> · Contemple Cristo<br>
    Você recebeu este e-mail porque se inscreveu em beholdmovement.com.br. Para sair da lista, responda este e-mail pedindo a remoção.
  </td></tr>

</table>
</td></tr>
</table>
</body></html>`;

return [{
  json: {
    ...d,
    email_assunto: `Boas-vindas ao Behold Movement, ${d.primeiro_nome}!`,
    email_html: html,
    whatsapp_texto: linhas.join('\n'),
    etiquetas: ['behold-movement', etiqueta],
  },
}];
""".strip()

JS_ESCOLHER_CONTATO = r"""
// Procura, no resultado da busca do Chatwoot, o contato com o mesmo telefone.
const m = $('Montar mensagens').first().json;
const r = $input.first().json;
const lista = Array.isArray(r.payload) ? r.payload : [];
const digitos = (s) => String(s || '').replace(/\D/g, '');
const achado = lista.find((c) => digitos(c.phone_number) === digitos(m.telefone_e164));
return [{ json: { contact_id: achado ? achado.id : null } }];
""".strip()

JS_STATUS = r"""
// Resume o que deu certo e o que falhou, para gravar na planilha.
const d = $('Montar mensagens').first().json;
const email = $('Enviar e-mail de boas-vindas').first().json;
const conversa = $('Chatwoot: criar conversa').first().json;

const motivo = (o) => {
  const e = o && o.error;
  if (!e) return 'sem resposta';
  return String(e.message || e.description || e).slice(0, 120);
};

const okEmail = email && !email.error && email.id;
const okWhats = conversa && !conversa.error && conversa.id;

return [{
  json: {
    telefone_e164: d.telefone_e164,
    status_email: okEmail ? 'enviado' : 'erro: ' + motivo(email),
    status_whatsapp: okWhats ? 'enviado' : 'erro: ' + motivo(conversa),
    conversa_url: okWhats
      ? `${d.chatwoot_url}/app/accounts/${d.chatwoot_account_id}/conversations/${conversa.id}`
      : '',
  },
}];
""".strip()

# ------------------------------------------------------------ helpers de nós

COLUNAS = ["ID", "Data/hora", "Nome", "Telefone", "E-mail", "CEP", "Endereço", "Bairro",
           "Cidade", "Estado", "Igreja", "Ministério", "Consentimento", "Status e-mail",
           "Status WhatsApp", "Conversa Chatwoot", "Observações"]


def sheets_node(name, pos, values):
    schema = [{
        "id": c, "displayName": c, "required": False, "defaultMatch": False,
        "display": True, "type": "string", "canBeUsedToMatch": True,
        "removed": c not in values,
    } for c in COLUNAS]
    return {
        "parameters": {
            "operation": "appendOrUpdate",
            "documentId": {"__rl": True, "value": PLANILHA_ID, "mode": "id"},
            "sheetName": {"__rl": True, "value": "gid=1078546648", "mode": "list",
                          "cachedResultName": "Inscrições",
                          "cachedResultUrl": PLANILHA_URL + "#gid=1078546648"},
            "columns": {
                "mappingMode": "defineBelow",
                "value": values,
                "matchingColumns": ["Telefone"],
                "schema": schema,
            },
            "options": {"cellFormat": "RAW"},
        },
        "type": "n8n-nodes-base.googleSheets",
        "typeVersion": 4.5,
        "position": pos,
        "id": nid(name),
        "name": name,
        "credentials": {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets (conta do movimento)"}},
    }


def code_node(name, pos, js):
    return {
        "parameters": {"jsCode": js},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
        "id": nid(name),
        "name": name,
    }


def if_node(name, pos, left):
    return {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [{
                    "id": nid(name + "/cond"),
                    "leftValue": left,
                    "rightValue": "",
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": pos,
        "id": nid(name),
        "name": name,
    }


M = "$('Montar mensagens').first().json"
CW_BASE = f"={{{{ {M}.chatwoot_url }}}}/api/v1/accounts/{{{{ {M}.chatwoot_account_id }}}}"


def chatwoot_node(name, pos, method, path, body=None, query=None):
    params = {
        "method": method,
        "url": CW_BASE + path,
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "options": {"timeout": 20000},
    }
    if query:
        params["sendQuery"] = True
        params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
    if body:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = body
    return {
        "parameters": params,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos,
        "id": nid(name),
        "name": name,
        "onError": "continueRegularOutput",
        "credentials": {"httpHeaderAuth": {"id": "", "name": "Chatwoot API"}},
    }


def respond_node(name, pos, body, code=None):
    opts = {}
    if code is not None:
        opts["responseCode"] = code
    return {
        "parameters": {"respondWith": "json", "responseBody": body, "options": opts},
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1.1,
        "position": pos,
        "id": nid(name),
        "name": name,
    }


def build() -> dict:
    v = "$('Validar e padronizar').first().json"
    nodes = [
        {
            "parameters": {
                "content": (
                    "## Inscrições Behold Movement\n"
                    "Antes de ativar:\n"
                    "1. **Configurações**: preencha o ID da caixa de entrada do WhatsApp no Chatwoot e o link do grupo.\n"
                    "2. **Credenciais**: Google Sheets e Gmail com a conta do movimento; *Chatwoot API* como Header Auth "
                    "(nome `api_access_token`, valor = token do seu perfil no Chatwoot).\n"
                    "3. Nos dois nós da planilha, confira se a aba selecionada é **Inscrições**.\n"
                    "4. Ative o workflow. O site envia para `/webhook/behold-inscricao`."
                ),
                "height": 300, "width": 420, "color": 4,
            },
            "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
            "position": [-460, -340], "id": nid("nota"), "name": "Como configurar",
        },
        {
            "parameters": {
                "httpMethod": "POST",
                "path": "behold-inscricao",
                "responseMode": "responseNode",
                "options": {"allowedOrigins": SITE_ORIGENS},
            },
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [-460, 0],
            "id": nid("Inscrição no site"),
            "name": "Inscrição no site",
            "webhookId": nid("webhook/behold-inscricao"),
        },
        {
            "parameters": {
                "assignments": {"assignments": [
                    {"id": nid("cfg/url"), "name": "chatwoot_url", "value": "https://chatwoot.frontia.com.br", "type": "string"},
                    {"id": nid("cfg/acc"), "name": "chatwoot_account_id", "value": "1", "type": "string"},
                    {"id": nid("cfg/inbox"), "name": "chatwoot_inbox_id", "value": "PREENCHER", "type": "string"},
                    {"id": nid("cfg/grupo"), "name": "link_grupo", "value": "https://chat.whatsapp.com/PREENCHER", "type": "string"},
                    {"id": nid("cfg/remetente"), "name": "remetente_nome", "value": "Behold Movement", "type": "string"},
                    {"id": nid("cfg/treino-data"), "name": "treinamento_data", "value": "terça-feira, 27/10", "type": "string"},
                    {"id": nid("cfg/treino-hora"), "name": "treinamento_hora", "value": "20h", "type": "string"},
                    {"id": nid("cfg/treino-local"), "name": "treinamento_local", "value": "online, com o link enviado no grupo do WhatsApp", "type": "string"},
                ]},
                "options": {},
            },
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [-240, 0],
            "id": nid("Configurações"),
            "name": "Configurações",
        },
        code_node("Validar e padronizar", [-20, 0], JS_VALIDAR),
        if_node("Inscrição válida?", [200, 0], "={{ $json.valido }}"),
        respond_node(
            "Responder: dados inválidos", [420, 200],
            "={{ { ok: $json.bot, erros: $json.bot ? [] : $json.erros } }}",
            "={{ $json.bot ? 200 : 400 }}",
        ),
        sheets_node("Salvar na planilha", [420, -20], {
            "ID": f"={{{{ {v}.id }}}}",
            "Data/hora": f"={{{{ {v}.data_hora }}}}",
            "Nome": f"={{{{ {v}.nome }}}}",
            "Telefone": f"={{{{ {v}.telefone_e164 }}}}",
            "E-mail": f"={{{{ {v}.email }}}}",
            "CEP": f"={{{{ {v}.cep }}}}",
            "Endereço": f"={{{{ {v}.endereco }}}}",
            "Bairro": f"={{{{ {v}.bairro }}}}",
            "Cidade": f"={{{{ {v}.cidade }}}}",
            "Estado": f"={{{{ {v}.uf }}}}",
            "Igreja": f"={{{{ {v}.igreja }}}}",
            "Ministério": f"={{{{ {v}.ministerio }}}}",
            "Consentimento": f"={{{{ {v}.consentimento }}}}",
            "Status e-mail": "pendente",
            "Status WhatsApp": "pendente",
        }),
        respond_node("Responder: inscrição recebida", [640, -20],
                     f"={{{{ {{ ok: true, id: {v}.id }} }}}}"),
        code_node("Montar mensagens", [860, -20], JS_MENSAGENS),
        {
            "parameters": {
                "sendTo": "={{ $json.email }}",
                "subject": "={{ $json.email_assunto }}",
                "emailType": "html",
                "message": "={{ $json.email_html }}",
                "options": {"appendAttribution": False, "senderName": "={{ $json.remetente_nome }}"},
            },
            "type": "n8n-nodes-base.gmail",
            "typeVersion": 2.1,
            "position": [1080, -20],
            "id": nid("Enviar e-mail de boas-vindas"),
            "name": "Enviar e-mail de boas-vindas",
            "webhookId": nid("gmail/boas-vindas"),
            "onError": "continueRegularOutput",
            "credentials": {"gmailOAuth2": {"id": "", "name": "Gmail (conta do movimento)"}},
        },
        {
            "parameters": {"amount": "={{ 15 + Math.floor(Math.random() * 45) }}", "unit": "seconds"},
            "type": "n8n-nodes-base.wait",
            "typeVersion": 1.1,
            "position": [1300, -20],
            "id": nid("Aguardar antes do WhatsApp"),
            "name": "Aguardar antes do WhatsApp",
            "webhookId": nid("wait/whatsapp"),
        },
        chatwoot_node("Chatwoot: buscar contato", [1520, -20], "GET", "/contacts/search",
                      query={"q": f"={{{{ {M}.telefone_e164.replace('+', '') }}}}"}),
        code_node("Escolher contato", [1740, -20], JS_ESCOLHER_CONTATO),
        if_node("Contato já existe?", [1960, -20], "={{ !!$json.contact_id }}"),
        chatwoot_node(
            "Chatwoot: criar contato", [2180, 140], "POST", "/contacts",
            body=(
                f"={{{{ JSON.stringify({{ inbox_id: Number({M}.chatwoot_inbox_id), name: {M}.nome, "
                f"phone_number: {M}.telefone_e164, additional_attributes: {{ city: {M}.cidade, "
                f"country: 'Brasil', description: 'Inscrição Behold Movement · Dia 31' }}, "
                f"custom_attributes: {{ igreja: {M}.igreja, ministerio: {M}.ministerio, "
                f"bairro: {M}.bairro, cidade: {M}.cidade, uf: {M}.uf, "
                f"email_inscricao: {M}.email }} }}) }}}}"
            ),
        ),
        chatwoot_node(
            "Chatwoot: criar conversa", [2400, -20], "POST", "/conversations",
            body=(
                f"={{{{ JSON.stringify({{ inbox_id: Number({M}.chatwoot_inbox_id), "
                f"contact_id: $json.contact_id ?? $json.payload?.contact?.id, "
                f"source_id: $json.payload?.contact_inbox?.source_id, status: 'open', "
                f"message: {{ content: {M}.whatsapp_texto }} }}) }}}}"
            ),
        ),
        chatwoot_node(
            "Chatwoot: etiquetas", [2620, -20], "POST",
            "/conversations/{{ $json.id }}/labels",
            body=f"={{{{ JSON.stringify({{ labels: {M}.etiquetas }}) }}}}",
        ),
        code_node("Resumir status", [2840, -20], JS_STATUS),
        sheets_node("Atualizar status na planilha", [3060, -20], {
            "Telefone": "={{ $json.telefone_e164 }}",
            "Status e-mail": "={{ $json.status_email }}",
            "Status WhatsApp": "={{ $json.status_whatsapp }}",
            "Conversa Chatwoot": "={{ $json.conversa_url }}",
        }),
    ]

    def link(*names):
        return {"main": [[{"node": n, "type": "main", "index": 0} for n in names]]}

    connections = {
        "Inscrição no site": link("Configurações"),
        "Configurações": link("Validar e padronizar"),
        "Validar e padronizar": link("Inscrição válida?"),
        "Inscrição válida?": {"main": [
            [{"node": "Salvar na planilha", "type": "main", "index": 0}],
            [{"node": "Responder: dados inválidos", "type": "main", "index": 0}],
        ]},
        "Salvar na planilha": link("Responder: inscrição recebida"),
        "Responder: inscrição recebida": link("Montar mensagens"),
        "Montar mensagens": link("Enviar e-mail de boas-vindas"),
        "Enviar e-mail de boas-vindas": link("Aguardar antes do WhatsApp"),
        "Aguardar antes do WhatsApp": link("Chatwoot: buscar contato"),
        "Chatwoot: buscar contato": link("Escolher contato"),
        "Escolher contato": link("Contato já existe?"),
        "Contato já existe?": {"main": [
            [{"node": "Chatwoot: criar conversa", "type": "main", "index": 0}],
            [{"node": "Chatwoot: criar contato", "type": "main", "index": 0}],
        ]},
        "Chatwoot: criar contato": link("Chatwoot: criar conversa"),
        "Chatwoot: criar conversa": link("Chatwoot: etiquetas"),
        "Chatwoot: etiquetas": link("Resumir status"),
        "Resumir status": link("Atualizar status na planilha"),
    }

    return {
        "name": "Behold Movement · Inscrições",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo"},
        "active": False,
        "pinData": {},
    }


def main() -> None:
    wf = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ok: {OUT.relative_to(ROOT)} ({len(wf['nodes'])} nós)")


if __name__ == "__main__":
    main()
