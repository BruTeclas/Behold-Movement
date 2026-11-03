// Testes dos workflows do n8n (pasta n8n/) com o simulador (scripts/simular-n8n.js).
// Nada real é chamado: Chatwoot, OpenAI e Google Sheets são simulados.
//
// Preparação (uma vez, numa pasta fora do repositório):
//   npm i luxon n8n-workflow@1 && npm pack @fazer-ai/n8n-nodes-chatwoot && tar -xzf fazer-ai-n8n-nodes-chatwoot-*.tgz
// Uso:
//   node scripts/testar-fluxos.js <pasta com node_modules> <pasta package/dist/nodes/Chatwoot>
'use strict';
const path = require('path');
const assert = require('assert');
const { criarSimulador } = require('./simular-n8n');

const [pastaModulos, pacoteFazer] = process.argv.slice(2);
if (!pastaModulos || !pacoteFazer) {
  console.error('uso: node scripts/testar-fluxos.js <pasta com node_modules> <pasta package/dist/nodes/Chatwoot>');
  process.exit(2);
}
const luxon = require(require.resolve('luxon', { paths: [pastaModulos] }));
const { DateTime } = luxon;
const agora = () => DateTime.now().setZone('America/Sao_Paulo');
const dataHora = (horasAtras) => agora().minus({ hours: horasAtras }).toFormat('yyyy-MM-dd HH:mm:ss');

// ---------------------------------------------------------------- serviços simulados
const planilha = { gravacoes: [], linhas: [] };
let respostasIA = [];
const respostasSite = [];
let iaChamadas = 0;

const textoBom = (m) => `Oi, ${m.primeiro_nome}! Que alegria ter você para servir ${({ Mídia: 'na', Evangelizando: 'no' })[m.ministerio] || 'na'} *${m.ministerio}*.\n\n`
  + `*Salve nosso contato* na agenda e responda com um 👍 quando salvar.\n\nEntre no grupo:\n${m.link_grupo}\n\n`
  + 'Treinamento: terça-feira, 27/10, às 20h, online.\n\nQualquer dúvida, é só escrever aqui. Contemple Cristo!';
const iaOk = (m) => ({ choices: [{ finish_reason: 'stop', message: { content: JSON.stringify({
  whatsapp: textoBom(m), email_assunto: `${m.primeiro_nome}, sua inscrição chegou!`,
  email_abertura: `Recebemos sua inscrição. Você vai servir na *${m.ministerio}* com a gente.` }), refusal: null } }] });
const iaErro = () => ({ error: { message: 'timeout of 45000ms exceeded' } });

const simulados = {
  'Salvar na planilha': async (itens, n, av) => itens.map((it) => {
    const linha = av(n.parameters.columns.value, it); planilha.gravacoes.push(['salvar', linha]); return { json: linha };
  }),
  'Atualizar status na planilha': async (itens, n, av) => itens.map((it) => {
    const linha = av(n.parameters.columns.value, it); planilha.gravacoes.push(['status', linha]); return { json: linha };
  }),
  'Ler planilha': async () => planilha.linhas.map((l, i) => ({ json: { row_number: i + 2, ...l } })),
  'IA: escrever mensagens': async (itens) => itens.map((it) => {
    iaChamadas++;
    const r = respostasIA.length > 1 ? respostasIA.shift() : respostasIA[0];
    return { json: r(it.json) };
  }),
  'n8n-nodes-base.respondToWebhook': async (itens, n, av) => {
    respostasSite.push({ codigo: av(n.parameters.options.responseCode ?? 200, itens[0]), corpo: av(n.parameters.responseBody, itens[0]) });
    return itens;
  },
  'Gerar planilha (.xlsx)': async (itens, n, av) => [{
    json: { linhas: itens.length },
    binary: { data: { data: Buffer.from(JSON.stringify(itens.map((i) => i.json))).toString('base64'),
      fileName: av(n.parameters.options.fileName, itens[0]), mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' } },
  }],
};

const sim = criarSimulador({
  pastaN8n: path.join(__dirname, '..', 'n8n'),
  pacoteFazer,
  luxon,
  simulados,
});
sim.porId['Behold Movement · Boas-vindas'] = 'behold-boas-vindas.json';
sim.porId['Behold Movement · WhatsApp para a equipe'] = 'behold-whatsapp-equipe.json';

// Chatwoot: contato novo, conversa nova, mensagens e arquivos aceitos
const chatwootBase = (extra = {}) => ({
  'POST /api/v1/accounts/1/inboxes/\\d+/on_whatsapp': { exists: true },
  'GET /api/v1/accounts/1/contacts/search': { payload: [] },
  'POST /api/v1/accounts/1/contacts': { payload: { contact: { id: 321 } } },
  'POST /api/v1/accounts/1/conversations': { id: 555, inbox_id: 7 },
  'GET /api/v1/accounts/1/inboxes/\\d+': { id: 7, provider: 'baileys', provider_connection: { connection: 'open' } },
  'POST /api/v1/accounts/1/conversations/\\d+/toggle_typing_status': {},
  'POST /api/v1/accounts/1/conversations/(\\d+)/messages': (corpo, chave) => ({ id: 9000 + sim.chamadas.length, conversation_id: Number(chave.split('/')[6]), content: corpo.content }),
  'GET /api/v1/accounts/1/conversations/\\d+': { labels: [] },
  'POST /api/v1/accounts/1/conversations/\\d+/labels': (corpo) => ({ payload: corpo.labels }),
  ...extra,
});

const inscricao = (extra = {}) => ({ body: {
  nome: 'maria', sobrenome: 'da silva', telefone: '(11) 91234-5678', telefone_e164: '+5511912345678', email: 'Maria@Exemplo.com',
  cep: '06010000', endereco: 'Rua A', numero: '1', bairro: 'centro', cidade: 'osasco', uf: 'sp', igreja: 'Igreja Teste',
  ministerio: 'Mídia', consentimento: 'sim', site: '', ...extra } });

const testes = [];
const teste = (nome, fn) => testes.push([nome, fn]);
const limpar = () => { planilha.gravacoes.length = 0; respostasSite.length = 0; iaChamadas = 0; };

// ---------------------------------------------------------------- inscrição + boas-vindas
teste('inscrição completa: grava, responde ao site, IA escreve e o WhatsApp sai', async () => {
  limpar(); sim.definirChatwoot(chatwootBase()); respostasIA = [iaOk];
  const wf = sim.carregar('behold-inscricao.json');
  await sim.rodar(wf, 'Inscrição no site', [{ json: inscricao() }]);
  assert.deepStrictEqual(respostasSite.map((r) => r.codigo), [200]);
  const salvar = planilha.gravacoes.find((g) => g[0] === 'salvar')[1];
  assert.strictEqual(salvar.Nome, 'Maria'); assert.strictEqual(salvar.Sobrenome, 'da Silva');
  const status = planilha.gravacoes.find((g) => g[0] === 'status')[1];
  assert.strictEqual(status['Status WhatsApp'], 'enviado');
  assert.strictEqual(status['Status e-mail'], 'desligado');
  const msg = sim.chamadas.find((c) => c.includes('/messages'));
  assert.ok(msg.includes('Salve nosso contato') && msg.includes('Oi, Maria!'), msg);
  assert.strictEqual(iaChamadas, 1);
});

teste('WhatsApp da caixa desconectado: não envia e marca erro (consulta do número)', async () => {
  limpar(); sim.definirChatwoot(chatwootBase({ 'POST /api/v1/accounts/1/inboxes/\\d+/on_whatsapp': new Error('Internal Server Error') }));
  respostasIA = [iaOk];
  await sim.rodar(sim.carregar('behold-inscricao.json'), 'Inscrição no site', [{ json: inscricao() }]);
  const status = planilha.gravacoes.find((g) => g[0] === 'status')[1];
  assert.ok(status['Status WhatsApp'].startsWith('erro (consulta do número)'), status['Status WhatsApp']);
  assert.ok(!sim.chamadas.some((c) => c.includes('/messages')), 'não deveria enviar');
});

teste('IA falha 3 vezes: vai a mensagem fixa', async () => {
  limpar(); sim.definirChatwoot(chatwootBase()); respostasIA = [iaErro];
  await sim.rodar(sim.carregar('behold-inscricao.json'), 'Inscrição no site', [{ json: inscricao() }]);
  assert.strictEqual(iaChamadas, 3);
  const msg = sim.chamadas.find((c) => c.includes('/messages'));
  assert.ok(msg.includes('Recebemos sua inscrição para servir na *Mídia*'), msg);
});

teste('dados inválidos e robô: responde e não chama as boas-vindas', async () => {
  limpar(); sim.definirChatwoot(chatwootBase());
  const wf = sim.carregar('behold-inscricao.json');
  await sim.rodar(wf, 'Inscrição no site', [{ json: { body: { nome: 'A', telefone: '1' } } }]);
  await sim.rodar(wf, 'Inscrição no site', [{ json: inscricao({ site: 'http://spam' }) }]);
  assert.deepStrictEqual(respostasSite.map((r) => r.codigo), [400, 200]);
  assert.strictEqual(planilha.gravacoes.length, 0);
  assert.strictEqual(sim.chamadas.length, 0);
});

// ---------------------------------------------------------------- reenvio
const linha = (nome, telefone, status, horasAtras, extra = {}) => ({
  ID: 'BHD-' + nome, 'Data/hora': dataHora(horasAtras), Nome: nome, Sobrenome: 'Teste', Telefone: telefone,
  'E-mail': nome.toLowerCase() + '@exemplo.com', Bairro: 'Centro', Cidade: 'Osasco', Estado: 'SP', Igreja: 'Igreja',
  'Ministério': 'Evangelizando', 'Status e-mail': 'desligado', 'Status WhatsApp': status, ...extra,
});

teste('reenvio: só quem tem erro recente (ou pendente parado) recebe de novo', async () => {
  limpar(); sim.definirChatwoot(chatwootBase()); respostasIA = [iaOk];
  planilha.linhas = [
    linha('Ana', '+5511900000001', 'erro (consulta do número): Internal Server Error', 30),
    linha('Bia', '+5511900000002', 'enviado', 30),
    linha('Caio', '+5511900000003', 'sem WhatsApp', 30),
    linha('Davi', '+5511900000004', 'erro (envio): x', 24 * 20),
    linha('Eva', '+5511900000005', 'pendente', 3),
    linha('Fabi', '+5511900000006', 'pendente', 0.2),
  ];
  const r = await sim.rodar(sim.carregar('behold-reenvio.json'), '4 vezes ao dia', [{ json: {} }]);
  const fila = r.execucoes['Quem precisa de reenvio'][0].map((i) => i.json.nome);
  assert.deepStrictEqual(fila, ['Ana', 'Eva']);
  const resumo = r.execucoes['Resumo do reenvio'][0][0].json;
  assert.strictEqual(resumo.enviados, 2); assert.strictEqual(resumo.continuam_com_erro, 0);
  const status = planilha.gravacoes.filter((g) => g[0] === 'status').map((g) => [g[1].Telefone, g[1]['Status WhatsApp']]);
  assert.deepStrictEqual(status, [['+5511900000001', 'enviado'], ['+5511900000005', 'enviado']]);
});

teste('reenvio com WhatsApp desconectado: não tenta ninguém e avisa por outra caixa, 1 vez por dia', async () => {
  limpar();
  const desconectado = chatwootBase({ 'GET /api/v1/accounts/1/inboxes/\\d+': { id: 7, provider_connection: { connection: 'close' } } });
  sim.definirChatwoot(desconectado); respostasIA = [iaOk];
  planilha.linhas = [linha('Ana', '+5511900000001', 'erro (consulta do número): x', 30)];
  const wf = sim.carregar('behold-reenvio.json');
  const cfg = wf.nodes.find((n) => n.name === 'Configurações do reenvio').parameters.assignments.assignments;
  cfg.find((a) => a.name === 'chatwoot_inbox_aviso').value = '6';
  cfg.find((a) => a.name === 'whatsapp_alerta').value = '(11) 98888-7777';
  await sim.rodar(wf, '4 vezes ao dia', [{ json: {} }]);
  assert.strictEqual(planilha.gravacoes.length, 0, 'não deveria reenviar');
  const avisos = sim.chamadas.filter((c) => c.includes('/messages'));
  assert.strictEqual(avisos.length, 1);
  assert.ok(sim.chamadas.some((c) => c.startsWith('POST /api/v1/accounts/1/conversations {') && c.includes('"inbox_id":"6"')), 'aviso deveria sair pela caixa 6');
  assert.ok(avisos[0].includes('desconectado'));
  sim.definirChatwoot(desconectado);
  await sim.rodar(wf, '4 vezes ao dia', [{ json: {} }]);
  assert.ok(!sim.chamadas.some((c) => c.includes('/messages')), 'segundo aviso no mesmo dia');
});

teste('reenvio com WhatsApp desconectado e sem caixa de aviso: não faz nada', async () => {
  limpar(); for (const k of Object.keys(sim.memoriaEstatica)) delete sim.memoriaEstatica[k];
  sim.definirChatwoot(chatwootBase({ 'GET /api/v1/accounts/1/inboxes/\\d+': { id: 7, provider_connection: { connection: 'close' } } }));
  planilha.linhas = [linha('Ana', '+5511900000001', 'erro (consulta do número): x', 30)];
  await sim.rodar(sim.carregar('behold-reenvio.json'), '4 vezes ao dia', [{ json: {} }]);
  assert.deepStrictEqual(sim.chamadas, ['GET /api/v1/accounts/1/inboxes/7']);
});

// ---------------------------------------------------------------- relatório
teste('relatório: com inscrição nova hoje, manda o .xlsx para cada número', async () => {
  limpar(); sim.definirChatwoot(chatwootBase());
  planilha.linhas = [linha('Ana', '+5511900000001', 'enviado', 1), linha('Bia', '+5511900000002', 'erro (envio): x', 50)];
  const wf = sim.carregar('behold-relatorio.json');
  wf.nodes.find((n) => n.name === 'Configurações do relatório').parameters.assignments.assignments
    .find((a) => a.name === 'whatsapp_destinatarios').value = '11 98888-7777, +55 21 97777-6666';
  await sim.rodar(wf, 'Todo dia às 21h', [{ json: {} }]);
  const arquivos = sim.chamadas.filter((c) => c.includes('/messages') && c.includes('<arquivo Behold-Inscricoes-'));
  assert.strictEqual(arquivos.length, 2, sim.chamadas.join('\n'));
  assert.ok(arquivos[0].includes('*1* inscrição nova hoje') && arquivos[0].includes('Ana Teste'), arquivos[0]);
  assert.ok(sim.chamadas.some((c) => c.includes('contacts/search ?q=5511988887777')));
  assert.ok(sim.chamadas.some((c) => c.includes('contacts/search ?q=5521977776666')));
});

teste('relatório: sem inscrição nova hoje, não manda nada', async () => {
  limpar(); sim.definirChatwoot(chatwootBase());
  planilha.linhas = [linha('Bia', '+5511900000002', 'enviado', 50)];
  const wf = sim.carregar('behold-relatorio.json');
  wf.nodes.find((n) => n.name === 'Configurações do relatório').parameters.assignments.assignments
    .find((a) => a.name === 'whatsapp_destinatarios').value = '11 98888-7777';
  await sim.rodar(wf, 'Todo dia às 21h', [{ json: {} }]);
  assert.strictEqual(sim.chamadas.length, 0);
});

(async () => {
  let falhas = 0;
  for (const [nome, fn] of testes) {
    try { await fn(); console.log('ok   ', nome); } catch (e) { falhas++; console.log('FALHA', nome, '\n     ', e.message.split('\n').slice(0, 6).join('\n      ')); }
  }
  console.log(falhas ? `\n${falhas} falha(s)` : '\ntodos os testes passaram');
  process.exit(falhas ? 1 : 0);
})();
