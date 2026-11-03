#!/usr/bin/env python3
"""Gera os workflows do n8n do Behold Movement (pasta n8n/).

behold-inscricao.json   site -> webhook -> valida e padroniza -> planilha (adiciona ou
                        atualiza pelo telefone) -> responde ao site -> chama "Boas-vindas".
behold-boas-vindas.json subfluxo: a IA (GPT, da OpenAI) escreve o e-mail e a mensagem de
                        WhatsApp a partir das instruções em Configurações, e o fluxo confere
                        o texto (tenta de novo; se não der, vai o texto fixo) -> e-mail
                        (Gmail, se email_ativo = sim) -> espera alguns segundos -> confere se
                        o número tem WhatsApp -> Chatwoot, pelo nó "Chatwoot fazer.ai"
                        (contato, conversa aberta ou nova, mensagem com "digitando..." antes,
                        etiquetas) -> grava na planilha o status de cada envio.
behold-reenvio.json     4 vezes ao dia: se o WhatsApp da caixa Behold estiver conectado, chama
                        "Boas-vindas" de novo para quem está com erro no WhatsApp; se estiver
                        desconectado, avisa a equipe por WhatsApp de outra caixa (uma vez por dia).
behold-relatorio.json   todo dia às 21h: se houve inscrição nova no dia, manda a planilha em
                        .xlsx pelo WhatsApp para os números da equipe.
behold-whatsapp-equipe.json  subfluxo: manda um texto (e um arquivo, se vier) para um número,
                        achando ou criando o contato e a conversa no Chatwoot.

Uso: python3 scripts/build-n8n.py
"""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASTA = ROOT / "n8n"

# ID do subfluxo "Behold Movement · Boas-vindas" no n8n (os fluxos de inscrição e de
# reenvio o chamam). Em outro n8n, troque pelo ID do subfluxo importado lá.
BOAS_VINDAS_ID = "OJAVeOzqoS78Xqd2"
# ID do subfluxo "Behold Movement · WhatsApp para a equipe" (relatório e aviso de desconexão).
EQUIPE_ID = "KXdsDekp2N0pY0Rc"

PLANILHA_ID = "1q1x8UUi4KOTB6ES8HToqCWhA9uCCkvchnFlU1ZWn8jE"
SITE_ORIGENS = "https://beholdmovement.com.br,https://www.beholdmovement.com.br"


def nid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "behold-n8n/" + name))


# O que a IA deve escrever. Fica no nó Configurações, para a equipe mudar no n8n.
# As conferências do nó "Conferir texto da IA" exigem nome, ministério, link do grupo
# e data/hora do treinamento; sem eles, vai o texto fixo.
IA_INSTRUCOES = """Escreva uma mensagem de boas-vindas calorosa e pessoal. Ela precisa ter:
- o primeiro nome da pessoa;
- a alegria pela inscrição e o ministério em que ela vai servir (por exemplo: servir na Mídia);
- o convite para entrar no grupo do WhatsApp do movimento, com o link, porque é lá que saem as notícias e as orientações do Dia 31;
- a data, o horário e o local do treinamento;
- o pedido, com destaque, para a pessoa salvar nosso contato na agenda e assim receber as próximas informações (por exemplo: *Salve nosso contato*);
- o pedido para a pessoa responder com um 👍 quando salvar nosso contato, e que ela pode escrever aqui se tiver dúvida.
Tom: alegre, acolhedor e simples, como uma conversa entre irmãos, sem exageros e sem cara de propaganda. Se quiser, feche com o lema do movimento: "Contemple Cristo e faça Cristo ser contemplado.\""""


# ---------------------------------------------------------------- JS dos nós

JS_VALIDAR = r"""
// Lê o formulário do site, padroniza os campos e diz se a inscrição é válida.
const b = $('Inscrição no site').first().json.body || {};

const limpa = (v) => String(v ?? '').trim().replace(/\s+/g, ' ');
const MINUSCULAS = ['da', 'de', 'do', 'das', 'dos', 'e'];
// "comeco" = o texto abre o nome; no sobrenome, "da", "de"... ficam minúsculos já na primeira palavra.
const capitaliza = (s, comeco = true) => limpa(s).toLowerCase().split(' ')
  .map((p, i) => ((i > 0 || !comeco) && MINUSCULAS.includes(p)) ? p : p.charAt(0).toUpperCase() + p.slice(1))
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
  sobrenome: capitaliza(b.sobrenome, false),
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
if (dados.nome.length < 2) erros.push('nome');
// A versão antiga do site não tem o campo sobrenome; nela, o sobrenome não é exigido.
if (b.sobrenome !== undefined && dados.sobrenome.length < 2) erros.push('sobrenome');
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
    // Quem escreve o nome completo em "Nome" e repete o sobrenome não fica com ele duplicado.
    nome_completo: dados.sobrenome && !(' ' + dados.nome).toLowerCase().endsWith(' ' + dados.sobrenome.toLowerCase())
      ? `${dados.nome} ${dados.sobrenome}` : dados.nome,
    telefone_e164: '+55' + digitos,
  },
}];
""".strip()

JS_MENSAGENS = r"""
// Monta os textos fixos (e-mail em HTML e mensagem de WhatsApp) e o pedido para a IA reescrevê-los.
const d = $('Configurações').first().json;   // dados da inscrição + configuração

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const etiqueta = 'frente-' + d.ministerio.normalize('NFD').replace(/[̀-ͯ]/g, '')
  .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

// Onde a pessoa vai servir: "na Mídia", "no Evangelizando"... Nunca "na frente de", que soa como liderar.
const ARTIGO = { 'Evangelizando': 'no', 'Mídia': 'na', 'Suprimento': 'no', 'Ação social': 'na', 'Intercessão': 'na' };
const artigo = ARTIGO[d.ministerio] || 'em';

// ---------- WhatsApp
const linhas = [
  `Olá, ${d.primeiro_nome}!`,
  '',
  `Aqui é do *Behold Movement*. Recebemos sua inscrição para servir ${artigo} *${d.ministerio}*. Que alegria ter você com a gente!`,
  '',
  '*Salve nosso contato* na sua agenda para receber as próximas informações do movimento.',
  '',
  'Entre no grupo do movimento para receber as notícias e as orientações do Dia 31:',
  d.link_grupo,
];
if (d.treinamento_data) {
  linhas.push('', `*Treinamento:* ${d.treinamento_data}, às ${d.treinamento_hora}, ${d.treinamento_local}.`);
}
linhas.push(
  '',
  'Responda com um 👍 quando salvar nosso contato. Se tiver alguma dúvida, é só escrever aqui.',
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

  <tr><td style="padding:32px 32px 16px;">
    <div style="font-family:${MONO};font-weight:bold;font-size:12px;letter-spacing:3px;color:${AZUL};">INSCRIÇÃO CONFIRMADA</div>
    <h1 style="margin:10px 0 16px;font-family:${DISPLAY};font-weight:normal;font-size:34px;line-height:1.05;color:${TINTA};text-transform:uppercase;">Que bom ter você com a gente, ${esc(d.primeiro_nome)}.</h1>
    <!--ABERTURA-->
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

// ---------- Pedido para a IA reescrever os textos (os de cima ficam de reserva)
const ESTILOS = [
  'comece pela alegria de ter a pessoa no movimento',
  'comece agradecendo a disposição de servir',
  'comece falando do ministério em que a pessoa vai servir',
  'comece com uma saudação curta e simples, e deixe o tom mais caloroso para o fim',
  'comece com uma frase de encorajamento sobre servir a Cristo',
  'comece pelo Dia 31 e pelo que ele significa',
];
const SISTEMA = [
  'Você escreve as mensagens de boas-vindas do Behold Movement, um movimento cristão de evangelismo, para quem acabou de se inscrever no site como voluntário. Escreva em português do Brasil.',
  'Cada mensagem deve parecer escrita à mão por alguém da equipe para aquela pessoa. Varie a abertura, a ordem das informações e as palavras de uma inscrição para outra, sem frases feitas que se repetiriam em todas as mensagens.',
  '',
  'O que a equipe pediu:',
  d.ia_instrucoes,
  '',
  'Regras que valem sempre:',
  '- Use só as informações dos dados da inscrição. Não invente datas, horários, lugares, links, nomes ou versículos.',
  '- No WhatsApp, o link do grupo aparece exatamente como foi fornecido, sozinho numa linha. Não coloque nenhum outro link.',
  '- WhatsApp: de 350 a 900 caracteres, parágrafos curtos, no máximo dois emojis e *negrito* do WhatsApp (um asterisco de cada lado) em no máximo três expressões, uma delas o pedido para salvar o contato. Não assine com nome de pessoa.',
  '- Sempre peça, em *negrito* e logo depois da saudação, que a pessoa salve nosso contato na agenda para receber as próximas informações, e peça que ela responda com um 👍 quando salvar. Isso é obrigatório: contato salvo evita que o WhatsApp trate a mensagem como spam.',
  '- Diga que a pessoa vai servir no ministério, com o artigo dos dados ("servir na Mídia", "servir no Evangelizando"). Nunca escreva "frente" nem "na frente de": soa como se ela fosse liderar.',
  '- Cite o primeiro nome e o ministério exatamente como estão nos dados. Cidade e igreja podem aparecer se soar natural; não é obrigatório.',
  '- E-mail: o assunto tem até 70 caracteres e cita o primeiro nome. A abertura tem um ou dois parágrafos curtos, separados por uma linha em branco, sem saudação (o título do e-mail já cumprimenta a pessoa pelo nome) e sem links: logo abaixo dela o e-mail já traz o botão do grupo, o treinamento e a programação do Dia 31.',
].join('\n');
const dadosInscricao = [
  'Dados da inscrição:',
  `- Primeiro nome: ${d.primeiro_nome}`,
  `- Ministério em que vai servir: ${d.ministerio} (escreva "servir ${artigo} ${d.ministerio}")`,
  `- Cidade: ${d.cidade}/${d.uf}`,
  `- Igreja onde congrega: ${d.igreja}`,
  `- Link do grupo do WhatsApp: ${d.link_grupo}`,
  `- Treinamento: ${d.treinamento_data
    ? `${d.treinamento_data}, às ${d.treinamento_hora}, ${d.treinamento_local}`
    : 'não há treinamento marcado; não mencione treinamento'}`,
  '',
  `Desta vez, ${ESTILOS[Math.floor(Math.random() * ESTILOS.length)]}.`,
].join('\n');

const ia_pedido = {
  model: d.ia_modelo || 'gpt-4.1-mini',
  messages: [
    { role: 'system', content: SISTEMA },
    { role: 'user', content: dadosInscricao },
  ],
  response_format: {
    type: 'json_schema',
    json_schema: {
      name: 'mensagens_boas_vindas',
      strict: true,
      schema: {
        type: 'object',
        properties: {
          whatsapp: { type: 'string', description: 'Mensagem de WhatsApp pronta para enviar.' },
          email_assunto: { type: 'string', description: 'Assunto do e-mail.' },
          email_abertura: { type: 'string', description: 'Um ou dois parágrafos que abrem o e-mail, separados por uma linha em branco.' },
        },
        required: ['whatsapp', 'email_assunto', 'email_abertura'],
        additionalProperties: false,
      },
    },
  },
};

return [{
  json: {
    ...d,
    email_assunto: `Boas-vindas ao Behold Movement, ${d.primeiro_nome}!`,
    email_abertura: `Sua inscrição no Behold Movement foi recebida. Você escolheu servir ${artigo} *${d.ministerio}*.\n\n`
      + 'As notícias, os avisos e as orientações do movimento são compartilhados no grupo do WhatsApp. Entre agora para não perder nada.',
    email_html: html,
    whatsapp_texto: linhas.join('\n'),
    etiquetas: ['behold-movement', etiqueta],
    ia_pedido,
  },
}];
""".strip()

JS_CONFERIR = r"""
// Usa os textos da IA quando passam nas conferências. Se a IA não respondeu ou o texto do WhatsApp
// foi recusado, pede de novo (loop pelo nó "Tentar a IA de novo?") até ia_tentativas vezes; depois
// disso, usa os textos fixos de "Montar mensagens".
const d = $('Montar mensagens').first().json;
const r = $input.first().json;
const tentativa = $runIndex + 1;            // este nó roda uma vez por tentativa
const maxTentativas = Math.max(1, Number(d.ia_tentativas) || 3);

const semAcento = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const contem = (texto, trecho) => semAcento(texto).includes(semAcento(trecho));
const links = (s) => (String(s).match(/https?:\/\/\S+/g) || []).map((l) => l.replace(/[.,;:!?)]+$/, ''));

// 1. A resposta da IA
let ia = null;
let motivo = '';
const escolha = Array.isArray(r.choices) ? r.choices[0] : null;
if (!escolha) {
  motivo = r.error ? 'erro na IA: ' + String(r.error.message || r.error.description || r.error).slice(0, 100)
    : d.ia_ativa === 'sim' ? 'resposta vazia da IA' : 'IA desligada';
} else if (escolha.message && escolha.message.refusal) {
  motivo = 'IA recusou';
} else if (escolha.finish_reason !== 'stop') {
  motivo = 'resposta incompleta (' + escolha.finish_reason + ')';
} else {
  try { ia = JSON.parse(escolha.message.content); } catch (e) { motivo = 'resposta fora do formato'; }
}

// 2. Conferências: o que precisa estar na mensagem e o que não pode aparecer
const problemasWhats = (t) => {
  if (typeof t !== 'string' || !t.trim()) return ['vazia'];
  const p = [];
  if (t.length < 200 || t.length > 1200) p.push(`tamanho ${t.length}`);
  if (!contem(t, d.primeiro_nome)) p.push('sem o nome');
  if (!contem(t, d.ministerio)) p.push('sem o ministério');
  if (/frente d[aeo]/.test(semAcento(t))) p.push('com "frente de"');
  if (!contem(t, 'salv') || !/contato|numero|agenda/.test(semAcento(t))) p.push('sem o pedido para salvar o contato');
  if (!contem(t, 'respond')) p.push('sem o pedido de resposta');
  if (!t.includes(d.link_grupo)) p.push('sem o link do grupo');
  if (links(t).some((l) => l !== d.link_grupo)) p.push('com outro link');
  if (d.treinamento_data) {
    const dia = (d.treinamento_data.match(/\d{1,2}\/\d{1,2}/) || [])[0];
    const hora = (String(d.treinamento_hora).match(/\d{1,2}/) || [])[0];
    if ((dia && !t.includes(dia)) || (hora && !t.includes(hora))) p.push('sem a data ou a hora do treinamento');
  }
  if (/[\[\]{}<>]/.test(t)) p.push('com marcação estranha');
  return p;
};
const problemasEmail = (assunto, abertura) => {
  if (typeof assunto !== 'string' || typeof abertura !== 'string') return ['vazio'];
  const p = [];
  if (assunto.trim().length < 5 || assunto.length > 90 || /\n/.test(assunto.trim())) p.push('assunto');
  if (abertura.trim().length < 60 || abertura.length > 900) p.push(`abertura com ${abertura.length} caracteres`);
  if (links(assunto + ' ' + abertura).length) p.push('com link');
  if (/frente d[aeo]/.test(semAcento(assunto + ' ' + abertura))) p.push('com "frente de"');
  if (/[\[\]{}<>]/.test(assunto + abertura)) p.push('com marcação estranha');
  return p;
};

let whatsapp = d.whatsapp_texto, assunto = d.email_assunto, abertura = d.email_abertura;
let origemWhats = 'modelo fixo: ' + motivo, origemEmail = origemWhats;
if (ia) {
  const w = String(ia.whatsapp ?? '').replace(/\*\*(.+?)\*\*/g, '*$1*').trim();
  const pw = problemasWhats(w);
  if (pw.length) origemWhats = 'modelo fixo: IA ' + pw.join(', ');
  else { whatsapp = w; origemWhats = 'IA'; }

  const pe = problemasEmail(ia.email_assunto, ia.email_abertura);
  if (pe.length) origemEmail = 'modelo fixo: IA ' + pe.join(', ');
  else { assunto = ia.email_assunto.trim(); abertura = ia.email_abertura.trim(); origemEmail = 'IA'; }
}

// 3. Parágrafos do e-mail (*texto* vira negrito)
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const P = 'margin:0 0 16px;font-family:Arial, Helvetica, sans-serif;font-size:16px;line-height:1.6;color:#16171c;';
const paragrafos = abertura.split(/\n\s*\n/).filter((p) => p.trim())
  .map((p) => `<p style="${P}">${esc(p.trim()).replace(/\*([^*\n]+)\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>')}</p>`)
  .join('\n    ');

// 4. Tentar de novo? Só quando a IA está ligada, o WhatsApp não veio dela e ainda há tentativas.
if (d.ia_ativa === 'sim' && origemWhats !== 'IA' && tentativa < maxTentativas) {
  const recusa = origemWhats.replace(/^modelo fixo: (IA )?/, '');
  const pedido = JSON.parse(JSON.stringify(d.ia_pedido));
  if (ia) {   // a IA respondeu, mas o texto foi recusado: diz a ela o que faltou
    pedido.messages[pedido.messages.length - 1].content +=
      `\n\nA versão anterior foi recusada (${recusa}). Escreva de novo, seguindo todas as regras.`;
  }
  return [{ json: { ...d, ia_pedido: pedido, tentar_de_novo: true, tentativa, motivo_nova_tentativa: recusa } }];
}
if (d.ia_ativa === 'sim') {
  origemWhats += origemWhats === 'IA' ? ` (tentativa ${tentativa})`
    : ` (depois de ${tentativa} tentativa${tentativa > 1 ? 's' : ''})`;
}

const { ia_pedido, ...resto } = d;
return [{
  json: {
    ...resto,
    tentar_de_novo: false,
    whatsapp_texto: whatsapp,
    email_assunto: assunto,
    email_abertura: abertura,
    email_html: d.email_html.replace('<!--ABERTURA-->', paragrafos),
    origem_textos: { whatsapp: origemWhats, email: origemEmail },
  },
}];
""".strip()

JS_ESCOLHER_CONTATO_BASE = r"""
// Procura, no resultado da busca do Chatwoot, o contato com o mesmo telefone.
const m = $('Conferir texto da IA').first().json;
const r = $input.first().json;
const lista = Array.isArray(r.payload) ? r.payload : [];
const digitos = (s) => String(s || '').replace(/\D/g, '');
const achado = lista.find((c) => digitos(c.phone_number) === digitos(m.telefone_e164));
return [{ json: { contact_id: achado ? achado.id : null } }];
""".strip()

JS_ESCOLHER_CONVERSA_BASE = r"""
// Reaproveita a conversa ainda aberta do contato na caixa do Behold; sem ela, o fluxo cria uma nova.
const m = $('Conferir texto da IA').first().json;
const contato = $('Escolher contato').first().json;
// O nó anterior devolve um item por conversa (ou um item vazio, se não houver nenhuma).
const lista = $input.all().map((i) => i.json).filter((c) => c && c.id);
const aberta = lista
  .filter((c) => String(c.inbox_id) === String(m.chatwoot_inbox_id) && c.status !== 'resolved')
  .sort((a, b) => (b.last_activity_at || 0) - (a.last_activity_at || 0))[0];
return [{ json: { contact_id: contato.contact_id, id: aberta ? aberta.id : null } }];
""".strip()

def js_escolher(base, origem):
    """Código de "Escolher contato"/"Escolher conversa" lendo telefone e caixa do nó `origem`."""
    return base.replace("$('Conferir texto da IA')", f"$('{origem}')")


JS_ESCOLHER_CONTATO = js_escolher(JS_ESCOLHER_CONTATO_BASE, "Conferir texto da IA")
JS_ESCOLHER_CONVERSA = js_escolher(JS_ESCOLHER_CONVERSA_BASE, "Conferir texto da IA")

JS_STATUS = r"""
// Resume o que deu certo e o que falhou, para gravar na planilha.
const d = $('Conferir texto da IA').first().json;

// Saída de um nó, ou null se ele não rodou nesta inscrição.
const saida = (nome) => {
  try { return $(nome).first().json; } catch (e) { return null; }
};
const motivo = (o) => {
  const e = o && o.error;
  if (!e) return 'sem resposta';
  return String(e.message || e.description || e).slice(0, 120);
};

let statusEmail = 'desligado';
if (d.email_ja_enviado) {
  statusEmail = 'enviado';   // reenvio: o e-mail já tinha ido
} else if (d.email_ativo === 'sim') {
  const email = saida('Enviar e-mail de boas-vindas');
  statusEmail = email && !email.error && email.id ? 'enviado' : 'erro: ' + motivo(email);
}

const ETAPAS = [
  ['WhatsApp: número existe?', 'consulta do número'],
  ['Chatwoot: buscar contato', 'busca do contato'],
  ['Chatwoot: criar contato', 'criação do contato'],
  ['Chatwoot: conversas do contato', 'busca da conversa'],
  ['Chatwoot: criar conversa', 'criação da conversa'],
  ['Chatwoot: enviar mensagem', 'envio'],
];
const consulta = saida('WhatsApp: número existe?');
const msg = saida('Chatwoot: enviar mensagem');
let statusWhats, conversaId = null;
if (consulta && consulta.exists === false) {
  statusWhats = 'sem WhatsApp';
} else if (msg && !msg.error && msg.id) {
  statusWhats = 'enviado';
  conversaId = msg.conversation_id;
} else {
  const falha = ETAPAS.map(([nome, etapa]) => [saida(nome), etapa]).find(([o]) => o && o.error);
  statusWhats = falha ? `erro (${falha[1]}): ${motivo(falha[0])}` : 'erro: ' + motivo(msg);
}

return [{
  json: {
    telefone_e164: d.telefone_e164,
    status_email: statusEmail,
    status_whatsapp: statusWhats,
    conversa_url: conversaId
      ? `${d.chatwoot_url}/app/accounts/${d.chatwoot_account_id}/conversations/${conversaId}`
      : '',
  },
}];
""".strip()

JS_FILA_REENVIO = r"""
// Quem vai para nova tentativa: Status WhatsApp com "erro" (ou parado em "pendente" há mais de
// 2 horas), inscrito nos últimos dias_para_tentar dias. "sem WhatsApp" e "enviado" ficam de fora.
const cfg = $('Configurações do reenvio').first().json;
const dias = Math.max(1, Number(cfg.dias_para_tentar) || 14);
const agora = DateTime.now().setZone('America/Sao_Paulo');
const limpa = (v) => String(v ?? '').trim();

const fila = [];
const vistos = new Set();
for (const { json: l } of $input.all()) {
  const status = limpa(l['Status WhatsApp']).toLowerCase();
  const quando = DateTime.fromFormat(limpa(l['Data/hora']), 'yyyy-MM-dd HH:mm:ss', { zone: 'America/Sao_Paulo' });
  if (!quando.isValid || agora.diff(quando, 'days').days > dias) continue;
  const parado = status === 'pendente' && agora.diff(quando, 'hours').hours >= 2;
  if (!status.startsWith('erro') && !parado) continue;
  const telefone = limpa(l['Telefone']);
  if (!/^\+55\d{10,11}$/.test(telefone) || vistos.has(telefone)) continue;
  vistos.add(telefone);

  const nome = limpa(l['Nome']);
  const sobrenome = limpa(l['Sobrenome']);
  fila.push({
    json: {
      id: limpa(l['ID']),
      data_hora: limpa(l['Data/hora']),
      nome,
      sobrenome,
      primeiro_nome: nome.split(' ')[0] || '',
      nome_completo: sobrenome && !(' ' + nome).toLowerCase().endsWith(' ' + sobrenome.toLowerCase())
        ? `${nome} ${sobrenome}` : nome,
      telefone_e164: telefone,
      email: limpa(l['E-mail']).toLowerCase(),
      bairro: limpa(l['Bairro']),
      cidade: limpa(l['Cidade']),
      uf: limpa(l['Estado']),
      igreja: limpa(l['Igreja']),
      ministerio: limpa(l['Ministério']),
      email_ja_enviado: limpa(l['Status e-mail']) === 'enviado',
      status_anterior: limpa(l['Status WhatsApp']),
    },
  });
}
return fila;
""".strip()

JS_RESUMO_REENVIO = r"""
// Quantas mensagens saíram nesta rodada (o subfluxo já gravou cada status na planilha).
const fila = $('Quem precisa de reenvio').all().map((i) => i.json);
const resultados = $input.all().map((i) => i.json);
const enviados = resultados.filter((r) => r['Status WhatsApp'] === 'enviado').length;
return [{
  json: {
    tentativas: fila.length,
    enviados,
    continuam_com_erro: fila.length - enviados,
    pessoas: fila.map((p, i) => `${p.nome_completo}: ${(resultados[i] || {})['Status WhatsApp'] || 'sem resposta'}`),
  },
}];
""".strip()

JS_AVISO_DESCONECTADO = r"""
// WhatsApp da caixa Behold desconectado (ou Chatwoot fora do ar): avisa a equipe pelo WhatsApp de
// OUTRA caixa (chatwoot_inbox_aviso), no máximo uma vez por dia. Sem essa caixa ou sem números, não avisa.
const cfg = $('Configurações do reenvio').first().json;
const numeros = String(cfg.whatsapp_alerta || '').split(/[,;]+/).map((t) => t.replace(/\D/g, '')).filter((t) => t.length >= 10);
if (!numeros.length || !String(cfg.chatwoot_inbox_aviso || '').trim()) return [];

const memoria = $getWorkflowStaticData('global');
const hoje = DateTime.now().setZone('America/Sao_Paulo').toFormat('yyyy-MM-dd');
if (memoria.ultimo_aviso === hoje) return [];
memoria.ultimo_aviso = hoje;

const r = $input.first().json;
const estado = r.error ? 'o Chatwoot não respondeu' : `a conexão está "${(r.provider_connection || {}).connection || 'desconhecida'}"`;
const texto = `⚠️ *Behold Movement*: o WhatsApp da caixa Behold está desconectado (${estado}).\n\n`
  + 'Para reconectar: no Chatwoot, *Configurações > Caixas de entrada > Behold*, gere o QR Code e leia com o WhatsApp '
  + 'do número do Behold (*Aparelhos conectados > Conectar um aparelho*).\n\n'
  + 'Quem ficou sem a mensagem de boas-vindas continua marcado com erro na planilha e recebe na próxima rodada depois que o WhatsApp voltar.';
return numeros.map((n) => ({
  json: {
    telefone_e164: '+' + (n.length <= 11 ? '55' + n : n),
    nome: 'Equipe Behold',
    texto,
    chatwoot_account_id: cfg.chatwoot_account_id,
    chatwoot_inbox_id: String(cfg.chatwoot_inbox_aviso).trim(),
  },
}));
""".strip()

JS_RELATORIO_DIA = r"""
// Só segue se houve inscrição hoje e há números na lista; passa adiante todas as linhas da planilha.
const cfg = $('Configurações do relatório').first().json;
const numeros = String(cfg.whatsapp_destinatarios || '').split(/[,;]+/).map((t) => t.replace(/\D/g, '')).filter((t) => t.length >= 10);
const hoje = DateTime.now().setZone('America/Sao_Paulo').toFormat('yyyy-MM-dd');
const linhas = $input.all().map((i) => i.json).filter((l) => String(l['ID'] || '').trim());
const novas = linhas.filter((l) => String(l['Data/hora'] || '').startsWith(hoje));
if (!numeros.length || !novas.length) return [];
return linhas.map(({ row_number, ...l }) => ({ json: l }));
""".strip()

JS_RELATORIO_MENSAGEM = r"""
// Uma mensagem por número da equipe: o resumo do dia vai como legenda do arquivo .xlsx.
const cfg = $('Configurações do relatório').first().json;
const numeros = String(cfg.whatsapp_destinatarios || '').split(/[,;]+/).map((t) => t.replace(/\D/g, '')).filter((t) => t.length >= 10);
const agora = DateTime.now().setZone('America/Sao_Paulo');
const hoje = agora.toFormat('yyyy-MM-dd');
const linhas = $('Inscrições do dia').all().map((i) => i.json);
const novas = linhas.filter((l) => String(l['Data/hora'] || '').startsWith(hoje));

const porMinisterio = Object.entries(linhas.reduce((m, l) => {
  const k = l['Ministério'] || '(vazio)'; m[k] = (m[k] || 0) + 1; return m;
}, {})).sort((a, b) => b[1] - a[1]).map(([k, n]) => `• ${k}: ${n}`).join('\n');
const semMensagem = linhas.filter((l) => String(l['Status WhatsApp'] || '').toLowerCase().startsWith('erro')).length;

const texto = [
  `📋 *Behold Movement · inscrições até ${agora.toFormat('dd/MM')}*`,
  '',
  `*${novas.length}* ${novas.length === 1 ? 'inscrição nova' : 'inscrições novas'} hoje · *${linhas.length}* no total.`,
  '',
  '*Novas hoje*',
  ...novas.map((l) => `• ${l['Nome']} ${l['Sobrenome'] || ''} · ${l['Ministério']} · ${l['Cidade']}/${l['Estado']}`.replace(/\s+·/g, ' ·')),
  '',
  '*Total por ministério*',
  porMinisterio,
  ...(semMensagem ? ['', `${semMensagem} ${semMensagem === 1 ? 'pessoa ainda está' : 'pessoas ainda estão'} sem a mensagem de boas-vindas; o reenvio automático tenta de novo 4 vezes ao dia.`] : []),
  '',
  'A planilha completa vai neste arquivo. É uma cópia: as alterações nos dados ficam com a equipe responsável.',
].join('\n');

const arquivo = $input.first().binary;
return numeros.map((n) => ({
  json: {
    telefone_e164: '+' + (n.length <= 11 ? '55' + n : n),
    nome: 'Equipe Behold',
    texto,
    chatwoot_account_id: cfg.chatwoot_account_id,
    chatwoot_inbox_id: cfg.chatwoot_inbox_id,
  },
  binary: arquivo,
}));
""".strip()

JS_JUNTAR_ARQUIVO = r"""
// Os nós do Chatwoot não repassam o arquivo: junta de novo o que chegou ao subfluxo.
const entrada = $('Dados do envio').first();
return [{ json: { ...$input.first().json, tem_arquivo: !!(entrada.binary && entrada.binary.data) }, binary: entrada.binary || {} }];
""".strip()

# ------------------------------------------------------------ helpers de nós

COLUNAS = ["ID", "Data/hora", "Nome", "Sobrenome", "Telefone", "E-mail", "CEP", "Endereço",
           "Bairro", "Cidade", "Estado", "Igreja", "Ministério", "Consentimento", "Status e-mail",
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
            # Aba pelo nome: com "gid=..." no modo lista, o nó não acha a aba ("Sheet with ID ... not found").
            "sheetName": {"__rl": True, "value": "Inscrições", "mode": "name"},
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


M = "$('Conferir texto da IA').first().json"


def por_id(expr):
    """Seletor de conta, caixa, contato ou conversa do nó fazer.ai, preenchido por ID."""
    return {"__rl": True, "value": expr, "mode": "id"}


CONTA = por_id(f"={{{{ {M}.chatwoot_account_id }}}}")
CAIXA = por_id(f"={{{{ {M}.chatwoot_inbox_id }}}}")


def chatwoot_node(titulo, pos, resource, operation, **params):
    """Nó "Chatwoot fazer.ai" (pacote @fazer-ai/n8n-nodes-chatwoot), instalado no n8n."""
    return {
        "parameters": {"resource": resource, "operation": operation, "accountId": CONTA, **params},
        "type": "@fazer-ai/n8n-nodes-chatwoot.chatwoot",
        "typeVersion": 1,
        "position": pos,
        "id": nid(titulo),
        "name": titulo,
        "onError": "continueRegularOutput",
        "credentials": {"fazerAiChatwootApi": {"id": "", "name": "Chatwoot fazer.ai · Behold"}},
    }


def ia_node(name, pos):
    """Pede à OpenAI (GPT) os textos; o pedido vem pronto de "Montar mensagens"."""
    return {
        "parameters": {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "openAiApi",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.ia_pedido) }}",
            "options": {"timeout": 45000},
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos,
        "id": nid(name),
        "name": name,
        "onError": "continueRegularOutput",
        "credentials": {"openAiApi": {"id": "", "name": "OpenAI"}},
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


def link(*names):
    return {"main": [[{"node": n, "type": "main", "index": 0} for n in names]]}


def nota(texto, pos, altura=300, largura=460):
    return {
        "parameters": {"content": texto, "height": altura, "width": largura, "color": 4},
        "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
        "position": pos, "id": nid("nota/" + texto[:40]), "name": "Como configurar",
    }


def subfluxo_node(name, pos, wf_id, wf_nome):
    """Chama um subfluxo uma vez por item e espera ele terminar."""
    return {
        "parameters": {
            "mode": "each",
            "workflowId": {"__rl": True, "value": wf_id, "mode": "id", "cachedResultName": wf_nome},
            "options": {"waitForSubWorkflow": True},
        },
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.3,
        "position": pos,
        "id": nid(name),
        "name": name,
        "onError": "continueRegularOutput",
    }


def agendamento_node(name, pos, cron):
    return {
        "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}},
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": pos,
        "id": nid(name),
        "name": name,
    }


def config_node(name, pos, valores):
    return {
        "parameters": {
            "assignments": {"assignments": [
                {"id": nid(f"{name}/{k}"), "name": k, "value": v, "type": "string"} for k, v in valores.items()
            ]},
            "options": {},
        },
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": pos,
        "id": nid(name),
        "name": name,
    }


def ler_planilha_node(name, pos):
    return {
        "parameters": {
            "documentId": {"__rl": True, "value": PLANILHA_ID, "mode": "id"},
            "sheetName": {"__rl": True, "value": "Inscrições", "mode": "name"},
            "options": {},
        },
        "type": "n8n-nodes-base.googleSheets",
        "typeVersion": 4.5,
        "position": pos,
        "id": nid(name),
        "name": name,
        "credentials": {"googleSheetsOAuth2Api": {"id": "", "name": "Google Sheets (conta do movimento)"}},
    }


def fluxo(nome, nodes, connections):
    return {
        "name": nome,
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "America/Sao_Paulo"},
        "active": False,
        "pinData": {},
    }


def build_inscricao() -> dict:
    v = "$('Validar e padronizar').first().json"
    nodes = [
        nota(
            "## Inscrições Behold Movement\n"
            "Recebe o formulário do site (`/webhook/behold-inscricao`), valida, grava na planilha, responde ao "
            "site e chama o subfluxo **Behold Movement · Boas-vindas**, que manda a mensagem de WhatsApp.\n\n"
            "A configuração das mensagens (link do grupo, treinamento, IA, e-mail) fica no nó **Configurações** "
            "do subfluxo.\n\n"
            "A planilha precisa ter os títulos das colunas exatamente como estão: se um título mudar, a "
            "inscrição falha ao salvar.",
            [-460, -380], altura=260),
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
        code_node("Validar e padronizar", [-240, 0], JS_VALIDAR),
        if_node("Inscrição válida?", [-20, 0], "={{ $json.valido }}"),
        respond_node(
            "Responder: dados inválidos", [200, 200],
            "={{ { ok: $json.bot, erros: $json.bot ? [] : $json.erros } }}",
            "={{ $json.bot ? 200 : 400 }}",
        ),
        sheets_node("Salvar na planilha", [200, -20], {
            "ID": f"={{{{ {v}.id }}}}",
            "Data/hora": f"={{{{ {v}.data_hora }}}}",
            "Nome": f"={{{{ {v}.nome }}}}",
            "Sobrenome": f"={{{{ {v}.sobrenome }}}}",
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
        respond_node("Responder: inscrição recebida", [420, -20],
                     f"={{{{ {{ ok: true, id: {v}.id }} }}}}"),
        {**code_node("Dados para as boas-vindas", [640, -20], "return [{ json: $('Validar e padronizar').first().json }];")},
        subfluxo_node("Enviar boas-vindas", [860, -20], BOAS_VINDAS_ID, "Behold Movement · Boas-vindas"),
    ]
    connections = {
        "Inscrição no site": link("Validar e padronizar"),
        "Validar e padronizar": link("Inscrição válida?"),
        "Inscrição válida?": {"main": [
            [{"node": "Salvar na planilha", "type": "main", "index": 0}],
            [{"node": "Responder: dados inválidos", "type": "main", "index": 0}],
        ]},
        "Salvar na planilha": link("Responder: inscrição recebida"),
        "Responder: inscrição recebida": link("Dados para as boas-vindas"),
        "Dados para as boas-vindas": link("Enviar boas-vindas"),
    }
    return fluxo("Behold Movement · Inscrições", nodes, connections)


def build_boas_vindas() -> dict:
    nodes = [
        nota(
            "## Boas-vindas (subfluxo)\n"
            "Chamado pelo fluxo de inscrição e pelo reenvio, com os dados de uma pessoa.\n\n"
            "1. **Configurações**: caixa do WhatsApp no Chatwoot (7 = Behold), link do grupo, treinamento, "
            "IA (`ia_ativa`, `ia_modelo`, `ia_tentativas`, `ia_instrucoes`) e e-mail (`email_ativo`).\n"
            "2. **Credenciais**: Google Sheets; Gmail (só com `email_ativo` = sim); *Chatwoot fazer.ai* (URL do "
            "Chatwoot e token do seu perfil); *OpenAI* (nó IA: escrever mensagens).\n\n"
            "**Textos com IA:** se a IA não responder ou esquecer nome, ministério, link ou treinamento, o fluxo "
            "pede de novo (até `ia_tentativas` vezes, com 5 s entre elas); depois disso, vai o texto fixo.\n\n"
            "**WhatsApp:** se o número não tiver WhatsApp, a planilha marca *sem WhatsApp*; se a consulta falhar "
            "(caixa desconectada), marca *erro (consulta do número)* e o reenvio tenta de novo depois.",
            [420, -560], altura=420),
        {
            "parameters": {"inputSource": "passthrough"},
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1.2,
            "position": [420, -20],
            "id": nid("Dados da inscrição"),
            "name": "Dados da inscrição",
        },
        {
            "parameters": {
                "assignments": {"assignments": [
                    {"id": nid("cfg/url"), "name": "chatwoot_url", "value": "https://chatwoot.frontia.com.br", "type": "string"},
                    {"id": nid("cfg/acc"), "name": "chatwoot_account_id", "value": "1", "type": "string"},
                    {"id": nid("cfg/inbox"), "name": "chatwoot_inbox_id", "value": "7", "type": "string"},
                    {"id": nid("cfg/grupo"), "name": "link_grupo", "value": "https://chat.whatsapp.com/PREENCHER", "type": "string"},
                    {"id": nid("cfg/email-ativo"), "name": "email_ativo", "value": "não", "type": "string"},
                    {"id": nid("cfg/remetente"), "name": "remetente_nome", "value": "Behold Movement", "type": "string"},
                    {"id": nid("cfg/treino-data"), "name": "treinamento_data", "value": "terça-feira, 27/10", "type": "string"},
                    {"id": nid("cfg/treino-hora"), "name": "treinamento_hora", "value": "20h", "type": "string"},
                    {"id": nid("cfg/treino-local"), "name": "treinamento_local", "value": "online, com o link enviado no grupo do WhatsApp", "type": "string"},
                    {"id": nid("cfg/ia-ativa"), "name": "ia_ativa", "value": "sim", "type": "string"},
                    {"id": nid("cfg/ia-modelo"), "name": "ia_modelo", "value": "gpt-4.1-mini", "type": "string"},
                    {"id": nid("cfg/ia-tentativas"), "name": "ia_tentativas", "value": "3", "type": "string"},
                    {"id": nid("cfg/ia-instrucoes"), "name": "ia_instrucoes", "value": IA_INSTRUCOES, "type": "string"},
                ]},
                "includeOtherFields": True,
                "options": {},
            },
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [640, -20],
            "id": nid("Configurações"),
            "name": "Configurações",
        },
        code_node("Montar mensagens", [860, -20], JS_MENSAGENS),
        if_node("Escrever com IA?", [1080, -20], "={{ $json.ia_ativa === 'sim' }}"),
        ia_node("IA: escrever mensagens", [1300, -120]),
        code_node("Conferir texto da IA", [1520, -20], JS_CONFERIR),
        if_node("Tentar a IA de novo?", [1740, -20], "={{ $json.tentar_de_novo === true }}"),
        {
            "parameters": {"amount": 5, "unit": "seconds"},
            "type": "n8n-nodes-base.wait",
            "typeVersion": 1.1,
            "position": [1520, -260],
            "id": nid("Aguardar nova tentativa"),
            "name": "Aguardar nova tentativa",
            "webhookId": nid("wait/nova-tentativa"),
        },
        if_node("Enviar e-mail?", [1960, -20], "={{ $json.email_ativo === 'sim' && !$json.email_ja_enviado }}"),
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
            "position": [2180, -120],
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
            "position": [2400, -20],
            "id": nid("Aguardar antes do WhatsApp"),
            "name": "Aguardar antes do WhatsApp",
            "webhookId": nid("wait/whatsapp"),
        },
        chatwoot_node("WhatsApp: número existe?", [2620, -20], "inbox", "onWhatsapp",
                      whatsappSpecialInboxId=CAIXA, phoneNumber=f"={{{{ {M}.telefone_e164 }}}}"),
        # Só segue com "exists: true". Se a consulta falhar (por exemplo, WhatsApp da caixa desconectado),
        # não tenta enviar: a planilha marca "erro (consulta do número)" e a inscrição pode ser reenviada.
        if_node("Tem WhatsApp?", [2840, -20], "={{ $json.exists === true }}"),
        chatwoot_node("Chatwoot: buscar contato", [3060, -20], "contact", "search",
                      searchQuery=f"={{{{ {M}.telefone_e164.replace('+', '') }}}}"),
        code_node("Escolher contato", [3280, -20], JS_ESCOLHER_CONTATO),
        if_node("Contato já existe?", [3500, -20], "={{ !!$json.contact_id }}"),
        {**chatwoot_node("Chatwoot: conversas do contato", [3720, -120], "contact", "listConversations",
                         contactId=por_id("={{ $json.contact_id }}")),
         "alwaysOutputData": True},
        code_node("Escolher conversa", [3940, -120], JS_ESCOLHER_CONVERSA),
        if_node("Conversa aberta?", [4160, -120], "={{ !!$json.id }}"),
        chatwoot_node(
            "Chatwoot: criar contato", [3720, 140], "contact", "create",
            name=f"={{{{ {M}.nome_completo }}}}",
            phoneNumber=f"={{{{ {M}.telefone_e164 }}}}",
            additionalFields={
                "city": f"={{{{ {M}.cidade }}}}",
                "country": "Brasil",
                "country_code": "BR",
                "description": "Inscrição Behold Movement · Dia 31",
            },
            specifyCustomAttributesCreate="json",
            customAttributesJsonCreate=(
                f"={{{{ JSON.stringify({{ igreja: {M}.igreja, ministerio: {M}.ministerio, "
                f"bairro: {M}.bairro, cidade: {M}.cidade, uf: {M}.uf, email_inscricao: {M}.email }}) }}}}"
            ),
        ),
        chatwoot_node("Chatwoot: criar conversa", [4380, 140], "conversation", "create",
                      inboxId=CAIXA,
                      contactId=por_id("={{ $json.contact_id ?? $json.payload?.contact?.id ?? $json.id }}")),
        chatwoot_node("Chatwoot: enviar mensagem", [4600, -20], "conversation", "sendMessage",
                      inboxId=CAIXA,
                      conversationId=por_id("={{ $json.id }}"),
                      content=f"={{{{ {M}.whatsapp_texto }}}}",
                      additionalFields={"wait_before_sending": "dynamic", "typing_while_waiting": True}),
        chatwoot_node("Chatwoot: etiquetas", [4820, -20], "conversation", "addLabels",
                      inboxId=CAIXA,
                      conversationId=por_id("={{ $json.conversation_id }}"),
                      labels=f"={{{{ {M}.etiquetas }}}}"),
        code_node("Resumir status", [5040, -20], JS_STATUS),
        sheets_node("Atualizar status na planilha", [5260, -20], {
            "Telefone": "={{ $json.telefone_e164 }}",
            "Status e-mail": "={{ $json.status_email }}",
            "Status WhatsApp": "={{ $json.status_whatsapp }}",
            "Conversa Chatwoot": "={{ $json.conversa_url }}",
        }),
    ]
    connections = {
        "Dados da inscrição": link("Configurações"),
        "Configurações": link("Montar mensagens"),
        "Montar mensagens": link("Escrever com IA?"),
        "Escrever com IA?": {"main": [
            [{"node": "IA: escrever mensagens", "type": "main", "index": 0}],
            [{"node": "Conferir texto da IA", "type": "main", "index": 0}],
        ]},
        "IA: escrever mensagens": link("Conferir texto da IA"),
        "Conferir texto da IA": link("Tentar a IA de novo?"),
        "Tentar a IA de novo?": {"main": [
            [{"node": "Aguardar nova tentativa", "type": "main", "index": 0}],
            [{"node": "Enviar e-mail?", "type": "main", "index": 0}],
        ]},
        "Aguardar nova tentativa": link("IA: escrever mensagens"),
        "Enviar e-mail?": {"main": [
            [{"node": "Enviar e-mail de boas-vindas", "type": "main", "index": 0}],
            [{"node": "Aguardar antes do WhatsApp", "type": "main", "index": 0}],
        ]},
        "Enviar e-mail de boas-vindas": link("Aguardar antes do WhatsApp"),
        "Aguardar antes do WhatsApp": link("WhatsApp: número existe?"),
        "WhatsApp: número existe?": link("Tem WhatsApp?"),
        "Tem WhatsApp?": {"main": [
            [{"node": "Chatwoot: buscar contato", "type": "main", "index": 0}],
            [{"node": "Resumir status", "type": "main", "index": 0}],
        ]},
        "Chatwoot: buscar contato": link("Escolher contato"),
        "Escolher contato": link("Contato já existe?"),
        "Contato já existe?": {"main": [
            [{"node": "Chatwoot: conversas do contato", "type": "main", "index": 0}],
            [{"node": "Chatwoot: criar contato", "type": "main", "index": 0}],
        ]},
        "Chatwoot: conversas do contato": link("Escolher conversa"),
        "Escolher conversa": link("Conversa aberta?"),
        "Conversa aberta?": {"main": [
            [{"node": "Chatwoot: enviar mensagem", "type": "main", "index": 0}],
            [{"node": "Chatwoot: criar conversa", "type": "main", "index": 0}],
        ]},
        "Chatwoot: criar contato": link("Chatwoot: criar conversa"),
        "Chatwoot: criar conversa": link("Chatwoot: enviar mensagem"),
        "Chatwoot: enviar mensagem": link("Chatwoot: etiquetas"),
        "Chatwoot: etiquetas": link("Resumir status"),
        "Resumir status": link("Atualizar status na planilha"),
    }
    return fluxo("Behold Movement · Boas-vindas", nodes, connections)


def build_reenvio() -> dict:
    nodes = [
        nota(
            "## Reenvio das boas-vindas\n"
            "Roda às 8h, 12h, 16h e 20h. Se o WhatsApp da caixa Behold estiver conectado, chama o subfluxo "
            "**Boas-vindas** para quem está com *erro* no Status WhatsApp (inscritos nos últimos "
            "`dias_para_tentar` dias). Deu certo: a planilha passa a *enviado*. Não deu: o erro fica, e a "
            "próxima rodada tenta de novo.\n\n"
            "Se o WhatsApp estiver desconectado, não tenta ninguém e avisa os números de `whatsapp_alerta` "
            "pelo WhatsApp de outra caixa do Chatwoot (`chatwoot_inbox_aviso`), no máximo uma vez por dia. "
            "Sem essa caixa ou sem números, não avisa.",
            [-460, -420], altura=300),
        agendamento_node("4 vezes ao dia", [-460, 0], "0 8,12,16,20 * * *"),
        config_node("Configurações do reenvio", [-240, 0], {
            "chatwoot_account_id": "1",
            "chatwoot_inbox_id": "7",
            "dias_para_tentar": "14",
            "chatwoot_inbox_aviso": "",
            "whatsapp_alerta": "",
        }),
        {**chatwoot_node("Chatwoot: caixa do WhatsApp", [-20, 0], "inbox", "get",
                         inboxId=por_id("={{ $('Configurações do reenvio').first().json.chatwoot_inbox_id }}")),
         "parameters": {
             "resource": "inbox", "operation": "get",
             "accountId": por_id("={{ $('Configurações do reenvio').first().json.chatwoot_account_id }}"),
             "inboxId": por_id("={{ $('Configurações do reenvio').first().json.chatwoot_inbox_id }}"),
         }},
        if_node("WhatsApp conectado?", [200, 0], "={{ $json.provider_connection?.connection === 'open' }}"),
        ler_planilha_node("Ler planilha", [420, -20]),
        code_node("Quem precisa de reenvio", [640, -20], JS_FILA_REENVIO),
        subfluxo_node("Enviar boas-vindas de novo", [860, -20], BOAS_VINDAS_ID, "Behold Movement · Boas-vindas"),
        code_node("Resumo do reenvio", [1080, -20], JS_RESUMO_REENVIO),
        code_node("Avisar: WhatsApp desconectado", [420, 200], JS_AVISO_DESCONECTADO),
        subfluxo_node("Enviar aviso", [640, 200], EQUIPE_ID, "Behold Movement · WhatsApp para a equipe"),
    ]
    connections = {
        "4 vezes ao dia": link("Configurações do reenvio"),
        "Configurações do reenvio": link("Chatwoot: caixa do WhatsApp"),
        "Chatwoot: caixa do WhatsApp": link("WhatsApp conectado?"),
        "WhatsApp conectado?": {"main": [
            [{"node": "Ler planilha", "type": "main", "index": 0}],
            [{"node": "Avisar: WhatsApp desconectado", "type": "main", "index": 0}],
        ]},
        "Ler planilha": link("Quem precisa de reenvio"),
        "Quem precisa de reenvio": link("Enviar boas-vindas de novo"),
        "Enviar boas-vindas de novo": link("Resumo do reenvio"),
        "Avisar: WhatsApp desconectado": link("Enviar aviso"),
    }
    return fluxo("Behold Movement · Reenvio das boas-vindas", nodes, connections)


def build_relatorio() -> dict:
    nodes = [
        nota(
            "## Relatório diário\n"
            "Todo dia às 21h: se houve inscrição nova no dia, manda a planilha completa em .xlsx pelo WhatsApp "
            "da caixa `chatwoot_inbox_id` (7 = Behold), com o resumo do dia na legenda, para os números de "
            "`whatsapp_destinatarios` (separados por vírgula, com DDD). Sem inscrição nova ou sem número, "
            "não manda nada.\n\n"
            "Assim a equipe acompanha as inscrições sem mexer na planilha original.",
            [-460, -360], altura=240),
        agendamento_node("Todo dia às 21h", [-460, 0], "0 21 * * *"),
        config_node("Configurações do relatório", [-240, 0], {
            "chatwoot_account_id": "1",
            "chatwoot_inbox_id": "7",
            "whatsapp_destinatarios": "",
        }),
        ler_planilha_node("Ler planilha", [-20, 0]),
        code_node("Inscrições do dia", [200, 0], JS_RELATORIO_DIA),
        {
            "parameters": {
                "operation": "xlsx",
                "binaryPropertyName": "data",
                "options": {
                    "fileName": "={{ 'Behold-Inscricoes-' + $now.setZone('America/Sao_Paulo').toFormat('yyyy-MM-dd') + '.xlsx' }}",
                    "sheetName": "Inscrições",
                },
            },
            "type": "n8n-nodes-base.convertToFile",
            "typeVersion": 1.1,
            "position": [420, 0],
            "id": nid("Gerar planilha (.xlsx)"),
            "name": "Gerar planilha (.xlsx)",
        },
        code_node("Montar mensagem do relatório", [640, 0], JS_RELATORIO_MENSAGEM),
        subfluxo_node("Enviar para a equipe", [860, 0], EQUIPE_ID, "Behold Movement · WhatsApp para a equipe"),
    ]
    connections = {
        "Todo dia às 21h": link("Configurações do relatório"),
        "Configurações do relatório": link("Ler planilha"),
        "Ler planilha": link("Inscrições do dia"),
        "Inscrições do dia": link("Gerar planilha (.xlsx)"),
        "Gerar planilha (.xlsx)": link("Montar mensagem do relatório"),
        "Montar mensagem do relatório": link("Enviar para a equipe"),
    }
    return fluxo("Behold Movement · Relatório diário", nodes, connections)


def build_whatsapp_equipe() -> dict:
    e = "$('Dados do envio').first().json"
    conta = por_id(f"={{{{ {e}.chatwoot_account_id }}}}")
    caixa = por_id(f"={{{{ {e}.chatwoot_inbox_id }}}}")
    nodes = [
        nota(
            "## WhatsApp para a equipe (subfluxo)\n"
            "Recebe `telefone_e164`, `nome`, `texto`, `chatwoot_account_id`, `chatwoot_inbox_id` e, se houver, "
            "um arquivo em `data`. Acha ou cria o contato e a conversa naquela caixa do Chatwoot e manda o "
            "arquivo com o texto de legenda (ou só o texto).\n\n"
            "Usado pelo relatório diário e pelo aviso de WhatsApp desconectado.",
            [-460, -380], altura=240),
        {
            "parameters": {"inputSource": "passthrough"},
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1.2,
            "position": [-460, 0],
            "id": nid("Dados do envio"),
            "name": "Dados do envio",
        },
        chatwoot_node("Chatwoot: buscar contato", [-240, 0], "contact", "search", accountId=conta,
                      searchQuery=f"={{{{ {e}.telefone_e164.replace('+', '') }}}}"),
        code_node("Escolher contato", [-20, 0], js_escolher(JS_ESCOLHER_CONTATO_BASE, "Dados do envio")),
        if_node("Contato já existe?", [200, 0], "={{ !!$json.contact_id }}"),
        {**chatwoot_node("Chatwoot: conversas do contato", [420, -120], "contact", "listConversations",
                         accountId=conta, contactId=por_id("={{ $json.contact_id }}")),
         "alwaysOutputData": True},
        code_node("Escolher conversa", [640, -120], js_escolher(JS_ESCOLHER_CONVERSA_BASE, "Dados do envio")),
        if_node("Conversa aberta?", [860, -120], "={{ !!$json.id }}"),
        chatwoot_node("Chatwoot: criar contato", [420, 140], "contact", "create", accountId=conta,
                      name=f"={{{{ {e}.nome || 'Equipe Behold' }}}}",
                      phoneNumber=f"={{{{ {e}.telefone_e164 }}}}"),
        chatwoot_node("Chatwoot: criar conversa", [1080, 140], "conversation", "create", accountId=conta,
                      inboxId=caixa,
                      contactId=por_id("={{ $json.contact_id ?? $json.payload?.contact?.id ?? $json.id }}")),
        code_node("Juntar arquivo", [1300, -20], JS_JUNTAR_ARQUIVO),
        if_node("Tem arquivo?", [1520, -20], "={{ $json.tem_arquivo === true }}"),
        chatwoot_node("Chatwoot: enviar arquivo", [1740, -120], "conversation", "sendFile", accountId=conta,
                      inboxId=caixa, conversationId=por_id("={{ $json.id }}"),
                      binaryPropertyName="data", isRecordedAudio=False,
                      fileCaption=f"={{{{ {e}.texto }}}}"),
        chatwoot_node("Chatwoot: enviar mensagem", [1740, 80], "conversation", "sendMessage", accountId=conta,
                      inboxId=caixa, conversationId=por_id("={{ $json.id }}"),
                      content=f"={{{{ {e}.texto }}}}"),
    ]
    connections = {
        "Dados do envio": link("Chatwoot: buscar contato"),
        "Chatwoot: buscar contato": link("Escolher contato"),
        "Escolher contato": link("Contato já existe?"),
        "Contato já existe?": {"main": [
            [{"node": "Chatwoot: conversas do contato", "type": "main", "index": 0}],
            [{"node": "Chatwoot: criar contato", "type": "main", "index": 0}],
        ]},
        "Chatwoot: conversas do contato": link("Escolher conversa"),
        "Escolher conversa": link("Conversa aberta?"),
        "Conversa aberta?": {"main": [
            [{"node": "Juntar arquivo", "type": "main", "index": 0}],
            [{"node": "Chatwoot: criar conversa", "type": "main", "index": 0}],
        ]},
        "Chatwoot: criar contato": link("Chatwoot: criar conversa"),
        "Chatwoot: criar conversa": link("Juntar arquivo"),
        "Juntar arquivo": link("Tem arquivo?"),
        "Tem arquivo?": {"main": [
            [{"node": "Chatwoot: enviar arquivo", "type": "main", "index": 0}],
            [{"node": "Chatwoot: enviar mensagem", "type": "main", "index": 0}],
        ]},
    }
    return fluxo("Behold Movement · WhatsApp para a equipe", nodes, connections)


ARQUIVOS = {
    "behold-inscricao.json": build_inscricao,
    "behold-boas-vindas.json": build_boas_vindas,
    "behold-reenvio.json": build_reenvio,
    "behold-relatorio.json": build_relatorio,
    "behold-whatsapp-equipe.json": build_whatsapp_equipe,
}


def main() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    for arquivo, construir in ARQUIVOS.items():
        wf = construir()
        nomes = {n["name"] for n in wf["nodes"]}
        for origem, saidas in wf["connections"].items():
            assert origem in nomes, (arquivo, origem)
            for destinos in saidas["main"]:
                for d in destinos:
                    assert d["node"] in nomes, (arquivo, d["node"])
        (PASTA / arquivo).write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"ok: n8n/{arquivo} ({len(wf['nodes'])} nós)")


if __name__ == "__main__":
    main()
