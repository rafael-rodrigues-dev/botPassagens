# ✈️ Bot de Alerta de Passagens Aéreas (Google Flights + Telegram Bot)

Este projeto monitora preços de passagens aéreas no **Google Flights** (com suporte estrito a **voos diretos / sem escalas**) e envia um alerta formatado no **Telegram** sempre que o valor ficar abaixo da sua meta.

---

## 🤖 Passo 1: Como criar seu Bot no Telegram (@BotFather)

1. Abra o Telegram e pesquise por **`@BotFather`** (ele tem um selo azul de verificado).
2. Envie o comando:
   ```text
   /newbot
   ```
3. O BotFather vai pedir um **nome de exibição** para o seu bot. Digite, por exemplo:
   ```text
   Alerta de Passagens
   ```
4. Em seguida, ele vai pedir um **username** (precisa terminar obrigatoriamente com `bot`). Digite, por exemplo:
   ```text
   rafael_passagens_bot
   ```
5. Pronto! O BotFather vai responder com duas coisas importantes:
   - Um **link** para o seu novo bot (ex: `t.me/rafael_passagens_bot`) -> **Clique nesse link e aperte em "Começar" (`Start`)** (isso é essencial para o bot poder te mandar mensagens).
   - O seu **HTTP API Token** (algo como `7123456789:AAHxyz...`).

---

## ⚙️ Passo 2: Configurar o `.env`

1. Abra o arquivo `.env` e cole o token que o `@BotFather` gerou:
   ```ini
   TELEGRAM_BOT_TOKEN=7123456789:AAHxyz...
   ```
2. **Não precisa procurar o seu `TELEGRAM_CHAT_ID` manualmente!** Depois de clicar em **Começar (`Start`)** no seu bot lá no Telegram, basta rodar o teste que o próprio script descobre o seu Chat ID sozinho e salva no `.env` automaticamente:
   ```bash
   python3 flight_alert.py --test-telegram
   ```

---

## 🚀 Como Usar

1. **Instalar as dependências:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Testar o envio de alerta no Telegram:**
   ```bash
   python3 flight_alert.py --test-telegram
   ```

3. **Executar uma busca única no Google Flights agora:**
   ```bash
   python3 flight_alert.py
   ```

4. **Deixar monitorando continuamente (ex: a cada 60 minutos):**
   ```bash
   python3 flight_alert.py --loop --interval 60
   ```

5. **Personalizar parâmetros via linha de comando:**
   ```bash
   python3 flight_alert.py \
     --origin GRU \
     --destination LHR \
     --departure 21/04/2027 \
     --return-date 26/04/2027 \
     --target-price 6000
   ```
