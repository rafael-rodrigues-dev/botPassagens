# ✈️ Bot de Alerta de Passagens Aéreas (Google Flights + WhatsApp Twilio)

Este projeto monitora preços de passagens aéreas no **Google Flights** (com suporte estrito a **voos diretos / sem escalas**) e envia um alerta formatado no **WhatsApp** via **Twilio** sempre que o valor ficar abaixo da sua meta.

---

## 📋 Pré-requisitos e Instalação

1. **Crie um ambiente virtual e instale as dependências:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure suas variáveis de ambiente:**
   Copie o arquivo `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```
   Edite o arquivo `.env` com suas credenciais do Twilio:
   - `TWILIO_ACCOUNT_SID`: Seu Account SID do painel Twilio.
   - `TWILIO_AUTH_TOKEN`: Seu Auth Token do painel Twilio.
   - `TWILIO_WHATSAPP_FROM`: Número do Sandbox do Twilio (ex: `whatsapp:+14155238886`).
   - `TWILIO_WHATSAPP_TO`: Seu número de WhatsApp (ex: `whatsapp:+5511999999999`).

   > **Nota sobre o Twilio Sandbox:** No console do Twilio (*Messaging -> Try it out -> Send a WhatsApp message*), envie o código de ativação (ex: `join <palavra-chave>`) do seu WhatsApp para o número do Sandbox para autorizar o recebimento de mensagens.

---

## 🚀 Como Usar

O script já vem configurado por padrão com o seu exemplo:
- **Trecho (Ida e Volta):** Guarulhos (`GRU`) ↔ Londres (`LHR`)
- **Voo:** `DIRETO` (`max_stops=0` / sem escalas)
- **Data Ida:** `21/04/2027` (`2027-04-21`)
- **Data Volta:** `26/04/2027` (`2027-04-26`)
- **Preço Alvo:** Abaixo de `R$ 6000`

### 1. Testar a formatação (Modo Simulação / Dry-Run)
Para testar a mensagem e o fluxo sem disparar o Twilio:
```bash
python3 flight_alert.py --test-whatsapp --dry-run
```

### 2. Testar o envio real no seu WhatsApp
Para enviar uma mensagem de teste real no seu WhatsApp e validar suas credenciais Twilio:
```bash
python3 flight_alert.py --test-whatsapp
```

### 3. Executar uma busca única agora
```bash
python3 flight_alert.py
```

### 4. Monitoramento contínuo (ex: verificar a cada 60 minutos)
```bash
python3 flight_alert.py --loop --interval 60
```

### 5. Personalizar parâmetros via linha de comando
Você também pode alterar datas, aeroportos ou preço alvo direto pelo terminal (aceita datas nos formatos `DD/MM/YYYY` ou `YYYY-MM-DD`):
```bash
python3 flight_alert.py \
  --origin GRU \
  --destination LHR \
  --departure 21/04/2027 \
  --return-date 26/04/2027 \
  --target-price 6000
```

