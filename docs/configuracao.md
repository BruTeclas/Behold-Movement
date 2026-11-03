# Behold Movement: site e inscrições

## Como funciona

1. A pessoa se inscreve em https://beholdmovement.com.br, de qualquer lugar do Brasil. Ao digitar o CEP, o site preenche rua, bairro, cidade e estado (serviço ViaCEP). Ao escolher o estado, o campo Cidade sugere os municípios daquele estado (IBGE). Se esses serviços estiverem fora do ar, a pessoa digita o endereço normalmente.
2. O site envia os dados para o n8n (`https://n8nai.frontia.com.br/webhook/behold-inscricao`).
3. O n8n valida os dados, grava na planilha [Behold Movement · Inscrições Dia 31](https://docs.google.com/spreadsheets/d/1q1x8UUi4KOTB6ES8HToqCWhA9uCCkvchnFlU1ZWn8jE/edit) e responde ao site.
4. Uma IA (GPT, da OpenAI) escreve o e-mail e a mensagem de WhatsApp daquela pessoa, seguindo as instruções da equipe (veja *Textos escritos pela IA*). Assim, cada pessoa recebe um texto diferente. Se a IA falhar ou esquecer alguma informação obrigatória, vai o texto fixo.
5. Se `email_ativo` = `sim`, o n8n manda o e-mail de boas-vindas pelo Gmail do movimento. Por enquanto está desligado (`não`): a inscrição segue só com o WhatsApp, e a planilha marca *desligado* em Status e-mail.
6. Depois de 15 a 60 segundos, o n8n fala com o Chatwoot pelos nós **Chatwoot fazer.ai** (pacote `@fazer-ai/n8n-nodes-chatwoot`):
   - pergunta à caixa **Behold** se o número tem WhatsApp; se não tiver, não envia nada e a planilha marca *sem WhatsApp*;
   - se essa consulta falhar (por exemplo, com o WhatsApp da caixa desconectado no Chatwoot), também não envia, e a planilha marca *erro (consulta do número)*; depois de reconectar, a inscrição pode ser reenviada;
   - procura o contato pelo telefone e cria se não existir;
   - usa a conversa aberta do contato na caixa Behold ou abre uma nova;
   - mostra "digitando..." por alguns segundos (proporcional ao tamanho do texto) e envia a mensagem de boas-vindas com o link do grupo;
   - coloca as etiquetas `behold-movement` e `frente-...` na conversa.
7. O n8n grava na planilha se o e-mail e o WhatsApp foram enviados ou deram erro.
8. Quem ficou com erro no WhatsApp recebe nova tentativa automática 4 vezes ao dia (veja *Reenvio automático*).
9. Às 21h, se houve inscrição nova no dia, a equipe recebe a planilha em .xlsx pelo WhatsApp (veja *Relatório diário*).

Se a mesma pessoa se inscrever de novo com o mesmo telefone, a linha dela na planilha é atualizada, e as mensagens de boas-vindas são enviadas outra vez.

**Não altere os títulos das colunas da aba Inscrições.** O n8n acha cada coluna pelo título; se um título mudar (em 30/10, "Nome" virou "6" por engano), todas as inscrições falham ao salvar. A equipe acompanha as inscrições pelo relatório diário, sem precisar abrir a planilha original.

## Arquivos

| Arquivo | O que é |
|---|---|
| `behold-movement.html` | Primeira versão do site (formato Artifact do Claude); só referência, não é publicada |
| `site/index.html`, `site/sites-incriveis.css`, `site/sites-incriveis.js` | O site publicado; edite estes arquivos diretamente |
| `deploy/coolify.Dockerfile` | Dockerfile autocontido para colar no Coolify (gerado) |
| `Dockerfile`, `deploy/nginx.conf` | Imagem do site quando o deploy vem do Git |
| `n8n/*.json` | Os 5 workflows do n8n (gerados; veja *Configurar o n8n*) |
| `scripts/build-site.py` | Gera `deploy/coolify.Dockerfile` a partir da pasta `site/` (não altera o site) |
| `scripts/build-n8n.py` | Gera os workflows do n8n |
| `scripts/build-planilha.py` | Gera o modelo da planilha (.xlsx) |
| `scripts/simular-n8n.js`, `scripts/testar-fluxos.js` | Simulador e testes dos workflows, sem tocar em nada real (veja *Testes*) |

Para mudar o site, edite os arquivos da pasta `site/` e publique de novo no Coolify (Redeploy). O treinamento (data, horário e local) fica no bloco `CONFIG.TREINAMENTO` de `site/index.html`.

## Publicar o site no Coolify (VPS)

O DNS de `beholdmovement.com.br` já aponta para o VPS (147.93.68.18), e o repositório no GitHub é público.

1. No Coolify, abra um projeto e clique em **+ New**, depois em **Public Repository**.
2. Repositório: `https://github.com/BruTeclas/Behold-Movement`, branch `main`.
3. Em **Build Pack**, escolha **Dockerfile** (o `Dockerfile` da raiz).
4. Em **Domains**, coloque `https://beholdmovement.com.br,https://www.beholdmovement.com.br`; em **Ports Exposes**, `80`.
5. Clique em **Deploy**. O Coolify gera o certificado HTTPS sozinho. Para atualizar o site depois, basta clicar em **Redeploy** (ou ligar o deploy automático).

Sem Git: em vez dos passos 1 a 3, escolha **+ New > Dockerfile** e cole o conteúdo de `deploy/coolify.Dockerfile`.

## Configurar o n8n

São 5 workflows, todos na pasta **Behold Movement** do n8n:

| Workflow | Arquivo | O que faz |
|---|---|---|
| **Behold Movement · Inscrições** (`aJKQuIUblegii7ze`) | `n8n/behold-inscricao.json` | Recebe o site, valida, grava na planilha, responde e chama *Boas-vindas* |
| **Behold Movement · Boas-vindas** (`OJAVeOzqoS78Xqd2`) | `n8n/behold-boas-vindas.json` | Subfluxo: IA, conferência, Chatwoot e status na planilha. Tem o nó **Configurações** |
| **Behold Movement · Reenvio das boas-vindas** (`jX45uItRMru83feT`) | `n8n/behold-reenvio.json` | 4 vezes ao dia, chama *Boas-vindas* de novo para quem está com erro |
| **Behold Movement · Relatório diário** (`nz5gV3OZGWZzZbk9`) | `n8n/behold-relatorio.json` | Às 21h, manda a planilha em .xlsx pelo WhatsApp para a equipe |
| **Behold Movement · WhatsApp para a equipe** (`KXdsDekp2N0pY0Rc`) | `n8n/behold-whatsapp-equipe.json` | Subfluxo: manda texto e arquivo para um número (relatório e aviso) |

As credenciais *Chatwoot fazer.ai · Behold*, *Google Sheets Novo*, *OpenAI* e *Gmail account* estão ligadas aos nós, e as etiquetas já existem no Chatwoot. Para importar em outro n8n: importe primeiro os dois subfluxos, troque `BOAS_VINDAS_ID` e `EQUIPE_ID` em `scripts/build-n8n.py` pelos IDs novos, rode o script e importe os outros três.

No n8n, depois de editar um workflow ativo, clique em **Publish** para a mudança valer.

1. **Configurações** (no subfluxo *Boas-vindas*):
   - `chatwoot_account_id`: o número que aparece na URL do Chatwoot, em `/app/accounts/NÚMERO/...` (hoje, 1).
   - `chatwoot_inbox_id`: em Chatwoot, *Configurações > Caixas de entrada*, abra a caixa do WhatsApp; o número fica na URL, em `/settings/inboxes/NÚMERO` (hoje, 7 = Behold, +55 11 99936-3542).
   - `link_grupo`: o link de convite do grupo do WhatsApp.
   - `treinamento_data`, `treinamento_hora`, `treinamento_local`: aparecem nas mensagens de boas-vindas. Deixe a data vazia para não mencionar o treinamento.
   - `email_ativo`: `sim` liga o e-mail de boas-vindas (precisa da credencial do Gmail); `não` desliga.
   - `ia_ativa`, `ia_modelo`, `ia_tentativas`, `ia_instrucoes`: veja *Textos escritos pela IA*.
2. **Credenciais:**
   - *Google Sheets*: conta Google com acesso à planilha. A planilha é de bru.teclas@gmail.com; compartilhe com o Gmail do movimento como Editor se for usar essa conta.
   - *Gmail* (só com `email_ativo` = `sim`): o Gmail novo do movimento, que é o remetente dos e-mails. No n8n: *Credentials > Create credential > Gmail OAuth2 API*, com o mesmo Client ID e Client Secret da credencial do Google Sheets, e *Sign in with Google* com a conta que envia. Se o Google recusar, ative a Gmail API no projeto do Google Cloud desse Client ID.
   - *Chatwoot fazer.ai*: credencial dos nós Chatwoot fazer.ai, com a URL do Chatwoot (`https://chatwoot.frontia.com.br`) e o token de acesso do seu perfil (no Chatwoot: avatar > *Profile settings* > *Access Token*).
   - *OpenAI*: a credencial da OpenAI que já existe no n8n (chave da API da OpenAI). Fica no nó **IA: escrever mensagens**.
3. Nos nós de planilha (**Salvar na planilha**, **Atualizar status na planilha** e **Ler planilha**, do reenvio e do relatório), a aba é escolhida pelo nome, **Inscrições**; se renomear a aba na planilha, mude também nesses nós. A planilha já está com as colunas certas, nesta ordem: ID, Data/hora, Nome, Sobrenome, Telefone, E-mail, CEP, Endereço, Bairro, Cidade, Estado, Igreja, Ministério, Consentimento, Status e-mail, Status WhatsApp, Conversa Chatwoot, Observações (veja `scripts/build-planilha.py`).
4. Ative o workflow e faça uma inscrição de teste com o seu próprio número.

## Reenvio automático

O workflow **Reenvio das boas-vindas** roda às 8h, 12h, 16h e 20h:

1. Lê a caixa do WhatsApp no Chatwoot (`chatwoot_inbox_id`, hoje 7 = Behold).
2. Se o WhatsApp estiver **conectado**, lê a planilha e pega quem tem *erro* no Status WhatsApp (ou ficou em *pendente* por mais de 2 horas), inscrito nos últimos `dias_para_tentar` dias (hoje 14). *sem WhatsApp* e *enviado* ficam de fora.
3. Para cada pessoa, chama o subfluxo *Boas-vindas*, o mesmo da inscrição, com espera de 15 a 60 segundos entre uma e outra. Deu certo: a planilha passa a *enviado*. Não deu: o erro fica, e a próxima rodada tenta de novo.
4. Se o WhatsApp estiver **desconectado**, não tenta ninguém e avisa a equipe, no máximo uma vez por dia, pelo WhatsApp de **outra** caixa do Chatwoot: `chatwoot_inbox_aviso` (o número da caixa) e `whatsapp_alerta` (os números que recebem, separados por vírgula, com DDD). Sem esses dois campos, não avisa.

Esses campos ficam no nó **Configurações do reenvio**. Se o e-mail de boas-vindas já tiver ido, o reenvio não manda o e-mail de novo.

## Relatório diário

O workflow **Relatório diário** roda às 21h. Se houve inscrição nova no dia, gera a planilha completa em .xlsx e manda pelo WhatsApp da caixa `chatwoot_inbox_id` (7 = Behold), com o resumo do dia na legenda: novas inscrições, total por ministério e quantas pessoas ainda estão sem a mensagem de boas-vindas.

Os números que recebem ficam em `whatsapp_destinatarios`, no nó **Configurações do relatório**, separados por vírgula e com DDD (por exemplo, `11 98888-7777, 11 97777-6666`). Para incluir ou tirar alguém, edite esse campo e clique em **Publish**. Sem inscrição nova no dia ou com a lista vazia, não manda nada.

## Testes

`scripts/testar-fluxos.js` roda os workflows da pasta `n8n/` num simulador: usa o código real dos nós e do pacote da fazer.ai, mas o Chatwoot, a OpenAI e a planilha são falsos, então nada real é chamado. Cobre inscrição, WhatsApp desconectado, IA falhando, reenvio, aviso e relatório.

```
# uma vez, numa pasta fora do repositório:
npm i luxon n8n-workflow@1 && npm pack @fazer-ai/n8n-nodes-chatwoot && tar -xzf fazer-ai-n8n-nodes-chatwoot-*.tgz
# depois, no repositório:
node scripts/testar-fluxos.js <essa pasta> <essa pasta>/package/dist/nodes/Chatwoot
```

## Textos escritos pela IA

Depois de salvar a inscrição, o nó **IA: escrever mensagens** pede ao GPT (modelo em `ia_modelo`, hoje `gpt-4.1-mini`) três textos: a mensagem de WhatsApp, o assunto do e-mail e os parágrafos de abertura do e-mail. O resto do e-mail (botão do grupo, treinamento e programação do Dia 31) continua fixo.

- **O que a mensagem deve conter** fica em `ia_instrucoes`, no nó Configurações. Edite esse texto à vontade: é o pedido que a IA recebe. O fluxo acrescenta regras fixas (não inventar datas nem links, tamanho da mensagem, link do grupo sozinho numa linha) e os dados da pessoa: primeiro nome, ministério, cidade, igreja, link do grupo e treinamento.
- **Variação:** a cada inscrição o fluxo sorteia um jeito diferente de começar a mensagem, e a IA não repete frases feitas. Assim as mensagens não saem iguais.
- **Conferência:** o nó **Conferir texto da IA** só aceita a mensagem de WhatsApp se ela tiver o primeiro nome, o ministério (sem a expressão "na frente de", que soa como liderar), o pedido para salvar nosso contato e responder com um 👍, o link do grupo exatamente como está em `link_grupo`, a data e a hora do treinamento (quando houver) e nenhum outro link. O e-mail não pode ter links. Se algo faltar, ou se a IA estiver fora do ar, vai o texto fixo. Na execução do n8n, o campo `origem_textos` mostra se cada texto veio da IA ou do modelo fixo, e por quê.
- **Novas tentativas (loop):** se a IA não responder (erro ou demora de mais de 45 s) ou o texto do WhatsApp for recusado na conferência, o nó **Tentar a IA de novo?** espera 5 segundos e pede outra vez; quando o texto foi recusado, a IA recebe o motivo. São até `ia_tentativas` chamadas (hoje 3). Se nenhuma der certo, vai o texto fixo. Em `origem_textos` aparece, por exemplo, "IA (tentativa 2)" ou "modelo fixo: ... (depois de 3 tentativas)".
- **Desligar:** `ia_ativa` = `não` faz o fluxo usar sempre o texto fixo.
- **Custo:** cada inscrição é uma chamada curta ao `gpt-4.1-mini`, cobrada na conta da OpenAI dona da chave. Para trocar de modelo, mude `ia_modelo` (precisa ser um modelo que aceite resposta em JSON Schema).
- **Dados enviados à OpenAI:** primeiro nome, ministério, cidade, igreja e o link do grupo. Telefone, e-mail e endereço não são enviados.

## Cuidados com o WhatsApp (API não oficial)

- O número pode ser bloqueado se mandar muitas mensagens para quem não tem o contato salvo. O workflow espera de 15 a 60 segundos antes de cada envio e pede para a pessoa salvar o número.
- Textos diferentes a cada envio (IA) ajudam, mas não bastam sozinhos. O que mais pesa para a Meta é a pessoa responder, salvar o número e não denunciar. Por isso a mensagem pede, em destaque, para salvar nosso contato e responder com um 👍. Responda quem escrever de volta pelo Chatwoot.
- Evite divulgar o formulário para listas muito grandes de uma vez só.
- Um grupo comum do WhatsApp aceita até 1.024 pessoas. Se passar disso, use uma Comunidade.
