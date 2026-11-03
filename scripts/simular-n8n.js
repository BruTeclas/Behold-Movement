// Simulador dos workflows do n8n do Behold Movement, para testar sem tocar em nada real.
//
// Percorre as ligações de um workflow (pasta n8n/) a partir de um nó, roda os nós de código e as
// expressões de verdade, roda o pacote da fazer.ai (nós "Chatwoot fazer.ai") contra um Chatwoot
// simulado e chama subfluxos. OpenAI, Google Sheets e outros serviços externos são simulados por
// funções passadas em `simulados`.
//
// Precisa de: npm i luxon   e do pacote @fazer-ai/n8n-nodes-chatwoot descompactado (npm pack).
// Uso: veja scripts/testar-fluxos.js.
'use strict';
const fs = require('fs');
const path = require('path');

function criarSimulador({ pastaN8n, pacoteFazer, luxon, simulados = {} }) {
  const { DateTime } = luxon;
  const transporte = require(path.join(pacoteFazer, 'shared/transport.js'));
  transporte.asyncSleep = async () => {};                       // nada de esperar de verdade
  const { Chatwoot } = require(path.join(pacoteFazer, 'Chatwoot.node.js'));
  const chamadas = [];                                           // HTTP feitas ao Chatwoot simulado
  const memoriaEstatica = {};

  const carregar = (arquivo) => JSON.parse(fs.readFileSync(path.join(pastaN8n, arquivo), 'utf8'));
  const porId = {};                                              // id do subfluxo -> arquivo (preenchido por quem usa)

  async function rodar(wf, inicio, itensIniciais) {
    const no = (n) => wf.nodes.find((x) => x.name === n) || (() => { throw new Error('nó não existe: ' + n); })();
    const execucoes = {};                                        // nome -> [[itens], ...] por rodada
    const $ = (nome) => ({
      first: () => { const r = execucoes[nome]; if (!r) throw new Error(`nó "${nome}" não rodou`); return r[r.length - 1][0]; },
      all: () => { const r = execucoes[nome]; if (!r) throw new Error(`nó "${nome}" não rodou`); return r[r.length - 1]; },
    });
    const ctxExpr = (item, runIndex) => ({ $, $json: item.json, $now: DateTime.now(), $runIndex: runIndex });
    function avaliar(v, item, runIndex) {
      if (typeof v === 'string' && v.startsWith('=')) {
        const corpo = v.slice(1);
        const c = ctxExpr(item, runIndex);
        const f = (code) => new Function(...Object.keys(c), 'return (' + code + ')')(...Object.values(c));
        const unico = corpo.match(/^\{\{([\s\S]+)\}\}$/);
        if (unico && !unico[1].includes('}}')) return f(unico[1]);
        return corpo.replace(/\{\{([\s\S]+?)\}\}/g, (_, code) => { const r = f(code); return typeof r === 'object' ? JSON.stringify(r) : String(r); });
      }
      if (Array.isArray(v)) return v.map((x) => avaliar(x, item, runIndex));
      if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, avaliar(x, item, runIndex)]));
      return v;
    }

    async function executar(n, itens, runIndex) {
      const t = n.type;
      const p = n.parameters || {};
      if (t === 'n8n-nodes-base.code') {
        const ctx = {
          $, $input: { first: () => itens[0], all: () => itens }, $runIndex: runIndex, DateTime,
          $getWorkflowStaticData: () => (memoriaEstatica[wf.name] = memoriaEstatica[wf.name] || {}),
        };
        const fn = new Function(...Object.keys(ctx), `return (async () => { ${p.jsCode} })()`);
        return [await fn(...Object.values(ctx))];
      }
      if (t === 'n8n-nodes-base.if') {
        const sim = [], nao = [];
        for (const it of itens) (avaliar(p.conditions.conditions[0].leftValue, it, runIndex) === true ? sim : nao).push(it);
        return [sim, nao];
      }
      if (t === 'n8n-nodes-base.set') {
        return [itens.map((it) => {
          const novos = Object.fromEntries(p.assignments.assignments.map((a) => [a.name, avaliar(a.value, it, runIndex)]));
          return { json: p.includeOtherFields ? { ...it.json, ...novos } : novos, binary: it.binary };
        })];
      }
      const repassa = ['n8n-nodes-base.wait', 'n8n-nodes-base.executeWorkflowTrigger', 'n8n-nodes-base.webhook',
        'n8n-nodes-base.scheduleTrigger'];
      if (repassa.includes(t)) return [itens];                  // gatilhos e esperas só repassam
      if (t === '@fazer-ai/n8n-nodes-chatwoot.chatwoot') {
        const saida = [];
        for (const it of itens) {
          const params = avaliar(p, it, runIndex);
          const ctx = {
            getInputData: () => [it],
            getNodeParameter: (nome, i, padrao) => {
              const v = nome.split('.').reduce((o, k) => (o == null ? undefined : o[k]), params);
              return v === undefined ? padrao : v;
            },
            getNode: () => ({ name: n.name, type: t }),
            getCredentials: async () => ({ url: 'https://chatwoot.exemplo', accessToken: 'x' }),
            continueOnFail: () => n.onError === 'continueRegularOutput',
            addExecutionHints: () => {},
            helpers: {
              httpRequestWithAuthentication: async (_c, o) => chatwoot(`${o.method} ${o.url}`, o.body, o.qs),
              requestWithAuthentication: async (_c, o) => chatwoot(`${o.method} ${o.uri.replace('https://chatwoot.exemplo', '')}`,
                { ...o.formData, 'attachments[]': `<arquivo ${o.formData['attachments[]'].options.filename}>` }),
              assertBinaryData: (_i, prop) => { const b = it.binary && it.binary[prop]; if (!b) throw new Error('sem arquivo em ' + prop); return b; },
              getBinaryDataBuffer: async (_i, prop) => Buffer.from(it.binary[prop].data || '', 'base64'),
            },
          };
          const r = await new Chatwoot().execute.call(ctx);
          let itensSaida = r[0].map((x) => ({ json: x.json }));
          if (!itensSaida.length && n.alwaysOutputData) itensSaida = [{ json: {} }];
          saida.push(...itensSaida);
        }
        return [saida];
      }
      if (t === 'n8n-nodes-base.executeWorkflow') {
        const arquivo = porId[p.workflowId.value] || porId[p.workflowId.cachedResultName];
        if (!arquivo) throw new Error('subfluxo sem arquivo: ' + p.workflowId.value);
        const sub = carregar(arquivo);
        const gatilho = sub.nodes.find((x) => x.type === 'n8n-nodes-base.executeWorkflowTrigger').name;
        const saida = [];
        for (const it of itens) saida.push(...(await rodar(sub, gatilho, [it])).ultimo);
        return [saida];
      }
      const simulado = simulados[n.name] || simulados[t];
      if (simulado) return [await simulado(itens, n, (v, it) => avaliar(v, it, runIndex))];
      throw new Error(`sem simulação para o nó "${n.name}" (${t})`);
    }

    let ultimo = [];
    const pilha = [[inicio, itensIniciais]];
    let passos = 0;
    while (pilha.length) {
      if (++passos > 500) throw new Error('loop sem fim');
      const [nome, itens] = pilha.pop();
      const n = no(nome);
      const runIndex = (execucoes[nome] || []).length;
      const saidas = await executar(n, itens, runIndex);
      execucoes[nome] = [...(execucoes[nome] || []), saidas[0]];
      const ligacoes = (wf.connections[nome] || { main: [] }).main;
      if (!ligacoes.some((l) => l && l.length)) ultimo = saidas[0];
      for (let s = saidas.length - 1; s >= 0; s--) {
        for (const destino of [...(ligacoes[s] || [])].reverse()) {
          if (saidas[s] && saidas[s].length) pilha.push([destino.node, saidas[s]]);
        }
      }
    }
    return { execucoes, ultimo };
  }

  let rotas = {};
  function chatwoot(chave, corpo, qs) {
    chamadas.push(chave + (corpo ? ' ' + JSON.stringify(corpo) : '') + (qs ? ' ?' + new URLSearchParams(qs) : ''));
    const r = Object.entries(rotas).find(([k]) => new RegExp('^' + k + '$').test(chave));
    if (!r) throw new Error('Chatwoot simulado não sabe responder: ' + chave);
    if (r[1] instanceof Error) throw r[1];
    return typeof r[1] === 'function' ? r[1](corpo, chave) : r[1];
  }

  return {
    carregar,
    porId,
    rodar,
    chamadas,
    memoriaEstatica,
    definirChatwoot: (novas) => { rotas = novas; chamadas.length = 0; },
  };
}

module.exports = { criarSimulador };
