# Pagamentos e doações

A Fase 7 adiciona duas entradas opcionais para doações externas. Nenhum SDK de pagamento é obrigatório: o Netrunner valida a assinatura do webhook, normaliza o pagamento e publica o mesmo evento `donation` usado pelo overlay de eventos.

## Configuração local

Defina as variáveis no ambiente do processo que executa o Netrunner:

```text
NETRUNNER_STREAMER_ID=local
NETRUNNER_PIX_WEBHOOK_SECRET=troque-por-um-segredo-longo
NETRUNNER_STRIPE_WEBHOOK_SECRET=whsec_troque-pelo-segredo-do-endpoint
```

`NETRUNNER_STREAMER_ID` identifica o destino deste Netrunner. O payload precisa carregar o mesmo valor; isso impede que uma confirmação assinada de outra conta seja associada ao overlay local. As chaves não são gravadas no projeto nem no ledger.

O servidor continua escutando apenas em `127.0.0.1`. Para receber webhooks externos, use um gateway HTTPS ou túnel controlado que encaminhe somente estas rotas; não exponha o servidor administrativo inteiro na internet.

## Pix

Endpoint: `POST /api/v1/webhooks/pix`

O contrato genérico espera uma confirmação com HMAC-SHA256 do corpo HTTP bruto no header `X-Netrunner-Signature` (também é aceito o prefixo opcional `sha256=`):

```json
{
  "id": "pix-abc-123",
  "status": "confirmed",
  "streamerId": "local",
  "amount": "25.00",
  "currency": "BRL",
  "donorName": "Alice",
  "message": "Valeu pela live!"
}
```

Também são aceitos `txid`, `transactionId` ou `e2eId` como identificador; `amountMinor`/`valorCentavos` para valores em centavos; e `metadata.streamer_id` para o destino. O status deve ser `confirmed`, `paid`, `completed`, `received` ou `settled`.

Cada gateway Pix pode ter nomes de campos e assinatura próprios. Nesse caso, o adaptador/gateway deve traduzir para este contrato e assinar o corpo encaminhado ao Netrunner.

## Stripe

Endpoint: `POST /api/v1/webhooks/stripe`

O endpoint entende a assinatura padrão `Stripe-Signature` no formato `t=<unix>,v1=<hmac>`, com tolerância de cinco minutos, e aceita os eventos:

- `payment_intent.succeeded`
- `checkout.session.completed`
- `charge.succeeded`

Configure `streamer_id` e, opcionalmente, `donation_id`, `donor_name` e `message` nos metadata do objeto Stripe. O valor é lido em unidades menores (`amount_received`, `amount_total` ou `amount`) e a moeda vem do objeto Stripe:

```json
{
  "id": "evt_123",
  "type": "payment_intent.succeeded",
  "data": {
    "object": {
      "id": "pi_123",
      "amount_received": 2500,
      "currency": "brl",
      "metadata": {
        "streamer_id": "local",
        "donation_id": "don-123",
        "donor_name": "Bob"
      }
    }
  }
}
```

## Evento comum e idempotência

Após a confirmação, o overlay recebe um evento como:

```json
{
  "type": "donation",
  "platform": "pix",
  "data": {
    "eventId": "pix:pix-abc-123",
    "donationId": "pix-abc-123",
    "provider": "pix",
    "streamerId": "local",
    "amount": "25.00",
    "amountMinor": 2500,
    "currency": "BRL",
    "user": "Alice",
    "displayName": "Alice",
    "title": "Doação recebida",
    "message": "Valeu pela live!",
    "status": "confirmed",
    "priority": 100
  }
}
```

O identificador de idempotência é `provider:externalId`. O Netrunner salva as últimas 2.000 confirmações em `donations.json`; reenviar o mesmo webhook retorna sucesso com `duplicate: true`, mas não cria um novo alerta.
