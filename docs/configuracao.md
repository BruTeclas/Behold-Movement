# Behold Movement: site e inscrições

## Como funciona

1. A pessoa se inscreve em https://beholdmovement.com.br, de qualquer lugar do Brasil. Ao digitar o CEP, o site preenche rua, bairro, cidade e estado (serviço ViaCEP). Ao escolher o estado, o campo Cidade sugere os municípios daquele estado (IBGE). Se esses serviços estiverem fora do ar, a pessoa digita o endereço normalmente.
2. O site envia os dados para o n8n (`https://n8nai.frontia.com.br/webhook/behold-inscricao`).
3. O n8n valida os dados, grava na planilha [Behold Movement · Inscrições Dia 31](https://docs.google.com/spreadsheets/d/1q1x8UUi4KOTB6ES8HToqCWhA9uCCkvchnFlU1ZWn8jE/edit) e responde ao site.
4. Uma IA (Claude, da Anthropic) escreve o e-mail e a mensagem de WhatsApp daquela pessoa, seguindo as instruções da equipe (veja *Textos escritos pela IA*). Assim, cada pessoa recebe um texto diferente. Se a IA falhar ou esquecer alguma informação obrigatória, vai o texto fixo.
5. O n8n manda o e-mail de boas-vindas pelo Gmail do movimento.
6. Depois de 15 a 60 segundos, o n8n cria o contato e a conversa no Chatwoot (caixa **Behold**) com a mensagem de boas-vindas e o link do grupo, e coloca as etiquetas `behold-movement` e `frente-...`. O Chatwoot entrega a mensagem pelo WhatsApp conectado.
7. O n8n grava na planilha se o e-mail e o WhatsApp foram enviados ou deram erro.

Se a mesma pessoa se inscrever de novo com o mesmo telefone, a linha dela na planilha é atualizada, e as mensagens de boas-vindas são enviadas outra vez.

## Arquivos

| Arquivo | O que é |
|---|---|
| `behold-movement.html` | Primeira versão do site (formato Artifact do Claude); só referência, não é publicada |
| `site/index.html`, `site/sites-incriveis.css`, `site/sites-incriveis.js` | O site publicado; edite estes arquivos diretamente |
| `deploy/coolify.Dockerfile` | Dockerfile autocontido para colar no Coolify (gerado) |
| `Dockerfile`, `deploy/nginx.conf` | Imagem do site quando o deploy vem do Git |
| `n8n/behold-inscricao.json` | Workflow para importar no n8n (gerado) |
| `scripts/build-site.py` | Gera `deploy/coolify.Dockerfile` a partir da pasta `site/` (não altera o site) |
| `scripts/build-n8n.py` | Gera o workflow do n8n |
| `scripts/build-planilha.py` | Gera o modelo da planilha (.xlsx) |

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

O workflow já está importado no n8n como **Behold Movement · Inscrições** (`https://n8nai.frontia.com.br/workflow/aJKQuIUblegii7ze`), ainda desativado. A credencial *Chatwoot API · Behold* já foi criada e ligada aos nós do Chatwoot, e as etiquetas já existem no Chatwoot. Para importar de novo em outro n8n: em Workflows, use *Import from File* com `n8n/behold-inscricao.json`.

1. **Configurações** (primeiro nó depois do webhook):
   - `chatwoot_account_id`: o número que aparece na URL do Chatwoot, em `/app/accounts/NÚMERO/...` (hoje, 1).
   - `chatwoot_inbox_id`: em Chatwoot, *Configurações > Caixas de entrada*, abra a caixa do WhatsApp; o número fica na URL, em `/settings/inboxes/NÚMERO` (hoje, 7 = Behold, +55 11 99936-3542).
   - `link_grupo`: o link de convite do grupo do WhatsApp.
   - `treinamento_data`, `treinamento_hora`, `treinamento_local`: aparecem nas mensagens de boas-vindas. Deixe a data vazia para não mencionar o treinamento.
   - `ia_ativa`, `ia_modelo`, `ia_instrucoes`: veja *Textos escritos pela IA*.
2. **Credenciais:**
   - *Google Sheets*: conta Google com acesso à planilha. A planilha é de bru.teclas@gmail.com; compartilhe com o Gmail do movimento como Editor se for usar essa conta.
   - *Gmail*: o Gmail novo do movimento, que é o remetente dos e-mails.
   - *Chatwoot API*: tipo **Header Auth**, nome `api_access_token`, valor = token de acesso do seu perfil no Chatwoot.
   - *Anthropic API*: tipo **Header Auth**, nome `x-api-key`, valor = uma chave criada em console.anthropic.com (*API Keys*). Escolha essa credencial no nó **IA: escrever mensagens**.
3. Nos nós **Salvar na planilha** e **Atualizar status na planilha**, confira se a aba escolhida é **Inscrições** (ID interno 1078546648). A planilha já está com as colunas certas, nesta ordem: ID, Data/hora, Nome, Telefone, E-mail, CEP, Endereço, Bairro, Cidade, Estado, Igreja, Ministério, Consentimento, Status e-mail, Status WhatsApp, Conversa Chatwoot, Observações (veja `scripts/build-planilha.py`).
4. Ative o workflow e faça uma inscrição de teste com o seu próprio número.

## Textos escritos pela IA

Depois de salvar a inscrição, o nó **IA: escrever mensagens** pede ao Claude (modelo em `ia_modelo`, hoje `claude-opus-5-5`) três textos: a mensagem de WhatsApp, o assunto do e-mail e os parágrafos de abertura do e-mail. O resto do e-mail (botão do grupo, treinamento e programação do Dia 31) continua fixo.

- **O que a mensagem deve conter** fica em `ia_instrucoes`, no nó Configurações. Edite esse texto à vontade: é o pedido que a IA recebe. O fluxo acrescenta regras fixas (não inventar datas nem links, tamanho da mensagem, link do grupo sozinho numa linha) e os dados da pessoa: primeiro nome, frente, cidade, igreja, link do grupo e treinamento.
- **Variação:** a cada inscrição o fluxo sorteia um jeito diferente de começar a mensagem, e a IA não repete frases feitas. Assim as mensagens não saem iguais.
- **Conferência:** o nó **Conferir texto da IA** só aceita a mensagem de WhatsApp se ela tiver o primeiro nome, a frente, o link do grupo exatamente como está em `link_grupo`, a data e a hora do treinamento (quando houver) e nenhum outro link. O e-mail não pode ter links. Se algo faltar, ou se a IA estiver fora do ar, vai o texto fixo. Na execução do n8n, o campo `origem_textos` mostra se cada texto veio da IA ou do modelo fixo, e por quê.
- **Desligar:** `ia_ativa` = `não` faz o fluxo usar sempre o texto fixo.
- **Custo:** com `claude-opus-5-5`, a estimativa é de US$ 0,02 a 0,04 por inscrição. Para gastar menos, troque `ia_modelo` para `claude-haiku-5-5`, que custa cerca de 30 vezes menos.
- **Dados enviados à Anthropic:** primeiro nome, frente, cidade, igreja e o link do grupo. Telefone, e-mail e endereço não são enviados.

## Cuidados com o WhatsApp (API não oficial)

- O número pode ser bloqueado se mandar muitas mensagens para quem não tem o contato salvo. O workflow espera de 15 a 60 segundos antes de cada envio e pede para a pessoa salvar o número.
- Textos diferentes a cada envio (IA) ajudam, mas não bastam sozinhos. O que mais pesa para a Meta é a pessoa responder, salvar o número e não denunciar. Por isso a mensagem convida a pessoa a responder. Responda quem escrever de volta pelo Chatwoot.
- Evite divulgar o formulário para listas muito grandes de uma vez só.
- Um grupo comum do WhatsApp aceita até 1.024 pessoas. Se passar disso, use uma Comunidade.
