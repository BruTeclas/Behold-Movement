# Behold Movement: site e inscrições

## Como funciona

1. A pessoa se inscreve em https://beholdmovement.com.br, de qualquer lugar do Brasil. Ao digitar o CEP, o site preenche rua, bairro, cidade e estado (serviço ViaCEP). Ao escolher o estado, o campo Cidade sugere os municípios daquele estado (IBGE). Se esses serviços estiverem fora do ar, a pessoa digita o endereço normalmente.
2. O site envia os dados para o n8n (`https://n8nai.frontia.com.br/webhook/behold-inscricao`).
3. O n8n valida os dados, grava na planilha [Behold Movement · Inscrições Dia 31](https://docs.google.com/spreadsheets/d/1q1x8UUi4KOTB6ES8HToqCWhA9uCCkvchnFlU1ZWn8jE/edit) e responde ao site.
4. O n8n manda o e-mail de boas-vindas pelo Gmail do movimento.
5. Depois de 15 a 60 segundos, o n8n cria o contato e a conversa no Chatwoot com a mensagem de boas-vindas e o link do grupo. O Chatwoot entrega a mensagem pelo WhatsApp conectado.
6. O n8n grava na planilha se o e-mail e o WhatsApp foram enviados ou deram erro.

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
2. Repositório: `https://github.com/BruTeclas/BruTeclas`, branch `claude/behold-movement-sketch-x7qf9h`.
3. Em **Build Pack**, escolha **Dockerfile** (o `Dockerfile` da raiz).
4. Em **Domains**, coloque `https://beholdmovement.com.br,https://www.beholdmovement.com.br`; em **Ports Exposes**, `80`.
5. Clique em **Deploy**. O Coolify gera o certificado HTTPS sozinho. Para atualizar o site depois, basta clicar em **Redeploy** (ou ligar o deploy automático).

Sem Git: em vez dos passos 1 a 3, escolha **+ New > Dockerfile** e cole o conteúdo de `deploy/coolify.Dockerfile`.

## Configurar o n8n

1. **Importar:** em Workflows, use *Import from File* com `n8n/behold-inscricao.json`.
2. **Configurações** (primeiro nó depois do webhook):
   - `chatwoot_account_id`: o número que aparece na URL do Chatwoot, em `/app/accounts/NÚMERO/...`.
   - `chatwoot_inbox_id`: em Chatwoot, *Configurações > Caixas de entrada*, abra a caixa do WhatsApp; o número fica na URL, em `/settings/inboxes/NÚMERO`.
   - `link_grupo`: o link de convite do grupo do WhatsApp.
   - `treinamento_data`, `treinamento_hora`, `treinamento_local`: aparecem nas mensagens de boas-vindas. Deixe a data vazia para não mencionar o treinamento.
3. **Credenciais:**
   - *Google Sheets*: conta Google com acesso à planilha. A planilha é de bru.teclas@gmail.com; compartilhe com o Gmail do movimento como Editor se for usar essa conta.
   - *Gmail*: o Gmail novo do movimento, que é o remetente dos e-mails.
   - *Chatwoot API*: tipo **Header Auth**, nome `api_access_token`, valor = token de acesso do seu perfil no Chatwoot.
4. Nos nós **Salvar na planilha** e **Atualizar status na planilha**, confira se a aba escolhida é **Inscrições** (ID interno 1078546648). A planilha já está com as colunas certas, nesta ordem: ID, Data/hora, Nome, Telefone, E-mail, CEP, Endereço, Bairro, Cidade, Estado, Igreja, Ministério, Consentimento, Status e-mail, Status WhatsApp, Conversa Chatwoot, Observações (veja `scripts/build-planilha.py`).
5. Ative o workflow e faça uma inscrição de teste com o seu próprio número.

## Cuidados com o WhatsApp (API não oficial)

- O número pode ser bloqueado se mandar muitas mensagens para quem não tem o contato salvo. O workflow espera de 15 a 60 segundos antes de cada envio e pede para a pessoa salvar o número.
- Evite divulgar o formulário para listas muito grandes de uma vez só.
- Um grupo comum do WhatsApp aceita até 1.024 pessoas. Se passar disso, use uma Comunidade.
