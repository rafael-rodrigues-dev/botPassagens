#!/usr/bin/env python3
"""
Bot de Monitoramento de Passagens Aéreas (Google Flights + Twilio WhatsApp)

Pesquisa passagens aéreas no Google Flights (com filtro estrito de voo direto)
e envia um alerta via WhatsApp usando a API do Twilio quando o preço atingir
o valor alvo configurado.
"""

import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

import urllib.request
import urllib.parse
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback simples para carregar arquivo .env caso python-dotenv ainda não esteja instalado
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
)
logger = logging.getLogger("botPassagens")


@dataclass
class FlightConfig:
    """Configurações da busca de passagens."""
    origin: str = "GRU"
    destination: str = "LHR"
    departure_date: str = "2027-04-21"  # Formato YYYY-MM-DD
    return_date: str = "2027-04-26"     # Formato YYYY-MM-DD (vazio se só ida)
    direct_only: bool = True            # True = Somente voos diretos (0 paradas)
    target_price: float = 6000.0        # Preço alvo em R$
    currency: str = "BRL"
    adults: int = 1
    seat_class: str = "economy"         # economy, premium-economy, business, first
    search_engine: str = "fast-flights" # "fast-flights" ou "serpapi"


@dataclass
class FlightOffer:
    """Representa uma oferta de voo encontrada."""
    airline: str
    price: float
    raw_price: str
    departure_time: str
    arrival_time: str
    duration: str
    stops: int
    booking_url: str


def normalize_date(date_str: str) -> str:
    """Converte datas DD/MM/YYYY para YYYY-MM-DD se necessário."""
    date_str = date_str.strip()
    if re.match(r"^\d{2}/\d{2}/\d{4}$", date_str):
        return datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    return date_str


def format_date_br(date_str: str) -> str:
    """Formata YYYY-MM-DD para DD/MM/YYYY para exibição."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return date_str


def parse_price(price_val) -> Optional[float]:
    """
    Extrai o valor numérico (float) de uma string de preço do Google Flights.
    Exemplos suportados:
      - "R$ 5.430" -> 5430.0
      - "R$ 5.430,50" -> 5430.50
      - "$1,250" -> 1250.0
      - 5430 -> 5430.0
    """
    if isinstance(price_val, (int, float)):
        return float(price_val)
    if not price_val or not isinstance(price_val, str):
        return None

    # Mantém apenas dígitos, pontos e vírgulas
    cleaned = re.sub(r"[^\d.,]", "", price_val.strip())
    if not cleaned:
        return None

    # Caso tenha ponto e vírgula (ex: 5.430,50 ou 5,430.50)
    if "." in cleaned and "," in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            # Formato BR/Europeu: 5.430,50
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # Formato US: 5,430.50
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Apenas vírgula: se termina com 2 dígitos (ex: 5430,50), é decimal; se 3 (ex: 5,430), é milhar
        parts = cleaned.split(",")
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "." in cleaned:
        # Apenas ponto: no Google Flights (ex: "R$ 5.430"), 3 dígitos após o ponto indica milhar
        parts = cleaned.split(".")
        if len(parts[-1]) == 3 and len(parts) >= 2:
            cleaned = cleaned.replace(".", "")

    try:
        value = float(cleaned)
        return value if value > 0 else None
    except ValueError:
        return None


def build_google_flights_url(config: FlightConfig) -> str:
    """Gera o link direto de pesquisa no Google Flights para abrir no navegador/celular."""
    stops_text = "nonstop" if config.direct_only else ""
    if config.return_date:
        query = (
            f"Flights from {config.origin} to {config.destination} "
            f"on {config.departure_date} through {config.return_date} {stops_text}"
        ).strip()
    else:
        query = (
            f"Flights from {config.origin} to {config.destination} "
            f"on {config.departure_date} {stops_text}"
        ).strip()
    return f"https://www.google.com/travel/flights?hl=pt-BR&curr={config.currency}&q={quote(query)}"


def search_with_fast_flights(config: FlightConfig) -> List[FlightOffer]:
    """
    Realiza a busca no Google Flights usando a biblioteca gratuita `fast-flights`.
    Suporta tanto a API v3.x (`FlightQuery` + `create_query`) quanto a API v2.x (`FlightData`).
    """
    try:
        import fast_flights
    except ImportError:
        logger.error(
            "A biblioteca 'fast-flights' não está instalada. "
            "Instale com: pip install -r requirements.txt"
        )
        return []

    booking_url = build_google_flights_url(config)
    max_stops = 0 if config.direct_only else None
    trip_type = "round-trip" if config.return_date else "one-way"
    result = None

    # 1. Tenta a sintaxe da versão 3.x (FlightQuery + create_query)
    if hasattr(fast_flights, "create_query") and hasattr(fast_flights, "FlightQuery"):
        from fast_flights import FlightQuery, Passengers, create_query, get_flights

        flights_queries = [
            FlightQuery(
                date=config.departure_date,
                from_airport=config.origin,
                to_airport=config.destination,
                max_stops=max_stops,
            )
        ]
        if config.return_date:
            flights_queries.append(
                FlightQuery(
                    date=config.return_date,
                    from_airport=config.destination,
                    to_airport=config.origin,
                    max_stops=max_stops,
                )
            )

        query = create_query(
            flights=flights_queries,
            trip=trip_type,
            seat=config.seat_class,
            passengers=Passengers(adults=config.adults),
            currency=config.currency,
        )
        result = get_flights(query)

    # 2. Fallback para a sintaxe da versão 2.x (FlightData + get_flights)
    else:
        from fast_flights import FlightData, Passengers, get_flights

        flight_data = [
            FlightData(
                date=config.departure_date,
                from_airport=config.origin,
                to_airport=config.destination,
                max_stops=max_stops,
            )
        ]
        if config.return_date:
            flight_data.append(
                FlightData(
                    date=config.return_date,
                    from_airport=config.destination,
                    to_airport=config.origin,
                    max_stops=max_stops,
                )
            )

        result = get_flights(
            flight_data=flight_data,
            trip=trip_type,
            seat=config.seat_class,
            passengers=Passengers(adults=config.adults),
            max_stops=max_stops,
            fetch_mode="common",
        )

    if result is None:
        return []

    # Extrai a lista de voos do objeto de retorno (compatível com v2 e v3)
    raw_flights = getattr(result, "flights", None)
    if raw_flights is None and isinstance(result, list):
        raw_flights = result
    if not raw_flights:
        return []

    offers: List[FlightOffer] = []
    for item in raw_flights:
        # Extrai preço
        raw_price_val = getattr(item, "price", None)
        price_num = parse_price(raw_price_val)
        if price_num is None:
            continue

        # Extrai paradas (stops)
        stops_val = getattr(item, "stops", 0)
        if isinstance(stops_val, str):
            if "nonstop" in stops_val.lower() or "direto" in stops_val.lower() or "0" in stops_val:
                stops_int = 0
            else:
                m = re.search(r"\d+", stops_val)
                stops_int = int(m.group(0)) if m else 1
        elif isinstance(stops_val, int):
            stops_int = stops_val
        else:
            # Em estruturas onde `flights` internos representam os segmentos de 1 trecho:
            sub_legs = getattr(item, "flights", [])
            stops_int = max(0, len(sub_legs) - 1) if isinstance(sub_legs, list) and sub_legs else 0

        # Garante filtro estrito de voo direto se solicitado
        if config.direct_only and stops_int != 0:
            continue

        # Extrai companhia aérea
        airline = getattr(item, "name", None) or getattr(item, "airlines", None)
        if isinstance(airline, list):
            airline = ", ".join(str(a) for a in airline)
        airline = str(airline) if airline else "Companhia não informada"

        # Extrai horários e duração
        departure_time = str(getattr(item, "departure", "N/A"))
        arrival_time = str(getattr(item, "arrival", "N/A"))
        duration = str(getattr(item, "duration", "N/A"))

        offers.append(
            FlightOffer(
                airline=airline,
                price=price_num,
                raw_price=str(raw_price_val),
                departure_time=departure_time,
                arrival_time=arrival_time,
                duration=duration,
                stops=stops_int,
                booking_url=booking_url,
            )
        )

    offers.sort(key=lambda o: o.price)
    return offers


def search_with_serpapi(config: FlightConfig) -> List[FlightOffer]:
    """
    Realiza a busca no Google Flights usando a API oficial do SerpApi (engine=google_flights).
    Útil caso deseje máxima estabilidade em servidores/cloud.
    """
    api_key = os.getenv("SERPAPI_KEY", "").strip()
    if not api_key:
        logger.error("Variável SERPAPI_KEY não configurada no arquivo .env.")
        return []

    params = {
        "engine": "google_flights",
        "departure_id": config.origin,
        "arrival_id": config.destination,
        "outbound_date": config.departure_date,
        "currency": config.currency,
        "hl": "pt-br",
        "gl": "br",
        "adults": config.adults,
        "type": "1" if config.return_date else "2",  # 1 = Ida e volta, 2 = Só ida
        "api_key": api_key,
    }
    if config.return_date:
        params["return_date"] = config.return_date
    if config.direct_only:
        params["stops"] = "1"  # No SerpApi Google Flights: 1 = Nonstop only (Voo direto)

    query_string = urllib.parse.urlencode(params)
    url = f"https://serpapi.com/search?{query_string}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    booking_url = data.get("search_metadata", {}).get("google_flights_url") or build_google_flights_url(config)
    all_flights = data.get("best_flights", []) + data.get("other_flights", [])

    offers: List[FlightOffer] = []
    for itinerary in all_flights:
        price_num = parse_price(itinerary.get("price"))
        if price_num is None:
            continue

        legs = itinerary.get("flights", [])
        layovers = itinerary.get("layovers", [])
        stops_int = len(layovers)

        if config.direct_only and stops_int != 0:
            continue

        airlines = list(dict.fromkeys(leg.get("airline", "") for leg in legs if leg.get("airline")))
        airline_str = ", ".join(airlines) if airlines else "Companhia não informada"

        first_leg = legs[0] if legs else {}
        last_leg = legs[-1] if legs else {}
        dep_time = first_leg.get("departure_airport", {}).get("time", "N/A")
        arr_time = last_leg.get("arrival_airport", {}).get("time", "N/A")
        total_min = itinerary.get("total_duration", 0)
        duration_str = f"{total_min // 60}h {total_min % 60}m" if total_min else "N/A"

        offers.append(
            FlightOffer(
                airline=airline_str,
                price=price_num,
                raw_price=f"{config.currency} {price_num:,.2f}",
                departure_time=dep_time,
                arrival_time=arr_time,
                duration=duration_str,
                stops=stops_int,
                booking_url=booking_url,
            )
        )

    offers.sort(key=lambda o: o.price)
    return offers


def search_flights(config: FlightConfig) -> List[FlightOffer]:
    """Direciona a pesquisa para o motor configurado (com fallback automático se houver chave SerpApi)."""
    engine = config.search_engine.lower().strip()
    if engine == "serpapi":
        return search_with_serpapi(config)

    try:
        offers = search_with_fast_flights(config)
        if offers:
            return offers
    except Exception as exc:
        logger.warning(f"Erro ao buscar via fast-flights: {exc}")

    # Se tiver SERPAPI_KEY configurada, usa como fallback automático
    if os.getenv("SERPAPI_KEY", "").strip():
        logger.info("Tentando fallback via SerpApi...")
        try:
            return search_with_serpapi(config)
        except Exception as exc:
            logger.error(f"Erro no fallback SerpApi: {exc}")

    return []


def format_whatsapp_message(config: FlightConfig, best_offer: FlightOffer, top_offers: List[FlightOffer]) -> str:
    """Formata a mensagem de alerta para envio no WhatsApp."""
    trecho_tipo = "Ida e Volta" if config.return_date else "Só Ida"
    voo_tipo = "DIRETO (Sem escalas)" if config.direct_only else f"{best_offer.stops} parada(s)"
    economia = config.target_price - best_offer.price

    linhas = [
        "✈️ *ALERTA DE PASSAGEM AÉREA!* ✈️",
        "",
        f"📍 *Trecho:* {config.origin} ↔ {config.destination} ({trecho_tipo})",
        f"🛑 *Tipo de Voo:* {voo_tipo}",
        f"📅 *Ida:* {format_date_br(config.departure_date)}",
    ]
    if config.return_date:
        linhas.append(f"📅 *Volta:* {format_date_br(config.return_date)}")

    linhas.extend([
        "",
        f"💰 *Menor Preço Encontrado:* R$ {best_offer.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"🎯 *Seu Preço Alvo:* R$ {config.target_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"📉 *Abaixo da meta em:* R$ {economia:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "",
        "🏆 *Detalhes da Melhor Opção:*",
        f"• *Companhia:* {best_offer.airline}",
        f"• *Partida:* {best_offer.departure_time}",
        f"• *Chegada:* {best_offer.arrival_time}",
        f"• *Duração:* {best_offer.duration}",
    ])

    if len(top_offers) > 1:
        linhas.append("")
        linhas.append("📋 *Outras opções diretas abaixo da meta:*")
        for idx, offer in enumerate(top_offers[1:3], start=2):
            preco_fmt = f"R$ {offer.price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            linhas.append(f"{idx}. {offer.airline} - {preco_fmt} ({offer.duration})")

    linhas.extend([
        "",
        f"🔗 *Ver no Google Flights:*",
        best_offer.booking_url,
    ])
    return "\n".join(linhas)


def send_whatsapp_alert(message_body: str, dry_run: bool = False) -> bool:
    """Envia mensagem de alerta via WhatsApp usando a API do Twilio."""
    if dry_run:
        logger.info("[MODO SIMULAÇÃO / DRY-RUN] Mensagem que seria enviada via WhatsApp:\n" + "-" * 50 + f"\n{message_body}\n" + "-" * 50)
        return True

    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_whatsapp = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886").strip()
    to_whatsapp = os.getenv("TWILIO_WHATSAPP_TO", "").strip()

    if not account_sid or not auth_token or not to_whatsapp:
        logger.error(
            "Credenciais do Twilio incompletas! Verifique TWILIO_ACCOUNT_SID, "
            "TWILIO_AUTH_TOKEN e TWILIO_WHATSAPP_TO no arquivo .env."
        )
        return False

    # Garante o prefixo "whatsapp:" exigido pelo Twilio
    if not from_whatsapp.startswith("whatsapp:"):
        from_whatsapp = f"whatsapp:{from_whatsapp}"
    if not to_whatsapp.startswith("whatsapp:"):
        to_whatsapp = f"whatsapp:{to_whatsapp}"

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=message_body,
            from_=from_whatsapp,
            to=to_whatsapp,
        )
        logger.info(f"✅ Alerta enviado com sucesso via WhatsApp! (Twilio SID: {message.sid})")
        return True
    except Exception as exc:
        logger.error(f"❌ Falha ao enviar mensagem pelo Twilio: {exc}")
        return False


def check_prices_and_notify(config: FlightConfig, dry_run: bool = False) -> bool:
    """
    Executa uma verificação completa no Google Flights e dispara o alerta no WhatsApp
    caso encontre voos abaixo do preço alvo.
    """
    tipo_voo_str = "DIRETO" if config.direct_only else "Qualquer (com ou sem escalas)"
    logger.info(
        f"🔎 Buscando passagens: {config.origin} <-> {config.destination} | "
        f"Ida: {format_date_br(config.departure_date)} | "
        f"Volta: {format_date_br(config.return_date)} | "
        f"Voo: {tipo_voo_str} | "
        f"Alvo: < R$ {config.target_price:.2f}"
    )

    offers = search_flights(config)

    if not offers:
        logger.warning("⚠️ Nenhum voo direto encontrado para os parâmetros informados no momento.")
        return False

    best_offer = offers[0]
    logger.info(
        f"💡 Menor preço atual encontrado: R$ {best_offer.price:.2f} "
        f"({best_offer.airline} | Duração: {best_offer.duration} | Paradas: {best_offer.stops})"
    )

    matching_offers = [o for o in offers if o.price < config.target_price]

    if matching_offers:
        logger.info(
            f"🎉 PREÇO ALVO ATINGIDO! Encontrado por R$ {best_offer.price:.2f} "
            f"(Alvo: abaixo de R$ {config.target_price:.2f}). Enviando alerta..."
        )
        msg = format_whatsapp_message(config, best_offer, matching_offers)
        return send_whatsapp_alert(msg, dry_run=dry_run)
    else:
        diff = best_offer.price - config.target_price
        logger.info(
            f"⏳ O menor preço (R$ {best_offer.price:.2f}) ainda está R$ {diff:.2f} "
            f"acima do alvo (< R$ {config.target_price:.2f}). Nenhum alerta enviado."
        )
        return False


def load_config_from_args() -> tuple[FlightConfig, argparse.Namespace]:
    """Lê parâmetros do .env e permite sobrescrevê-los via linha de comando."""
    parser = argparse.ArgumentParser(
        description="Monitora preços de passagens no Google Flights e envia alerta via WhatsApp (Twilio)."
    )
    parser.add_argument("--origin", default=os.getenv("ORIGIN", "GRU"), help="Aeroporto de origem (IATA, ex: GRU)")
    parser.add_argument("--destination", default=os.getenv("DESTINATION", "LHR"), help="Aeroporto de destino (IATA, ex: LHR)")
    parser.add_argument("--departure", default=os.getenv("DEPARTURE_DATE", "2027-04-21"), help="Data de ida (DD/MM/YYYY ou YYYY-MM-DD)")
    parser.add_argument("--return-date", default=os.getenv("RETURN_DATE", "2027-04-26"), help="Data de volta (DD/MM/YYYY ou YYYY-MM-DD)")
    parser.add_argument(
        "--allow-stops",
        action="store_true",
        help="Permite voos com escalas (por padrão busca APENAS voos DIRETOS)",
    )
    parser.add_argument(
        "--target-price",
        type=float,
        default=float(os.getenv("TARGET_PRICE", "6000")),
        help="Preço máximo alvo em R$ (padrão: 6000.0)",
    )
    parser.add_argument("--currency", default=os.getenv("CURRENCY", "BRL"), help="Moeda (padrão: BRL)")
    parser.add_argument(
        "--engine",
        choices=["fast-flights", "serpapi"],
        default=os.getenv("SEARCH_ENGINE", "fast-flights"),
        help="Motor de busca: 'fast-flights' (gratuito) ou 'serpapi'",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Mantém o script rodando continuamente em intervalos regulares",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.getenv("CHECK_INTERVAL_MINUTES", "60")),
        help="Intervalo em minutos entre buscas quando usado com --loop (padrão: 60)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa a busca real mas apenas exibe a mensagem no terminal sem chamar o Twilio",
    )
    parser.add_argument(
        "--test-whatsapp",
        action="store_true",
        help="Envia uma mensagem de teste imediata para validar suas credenciais do Twilio WhatsApp",
    )

    args = parser.parse_args()

    env_direct = os.getenv("DIRECT_FLIGHT_ONLY", "true").lower() in ("true", "1", "yes", "sim")
    direct_only = False if args.allow_stops else env_direct

    config = FlightConfig(
        origin=args.origin.upper().strip(),
        destination=args.destination.upper().strip(),
        departure_date=normalize_date(args.departure),
        return_date=normalize_date(args.return_date) if args.return_date else "",
        direct_only=direct_only,
        target_price=args.target_price,
        currency=args.currency.upper().strip(),
        search_engine=args.engine,
    )
    return config, args


def main():
    config, args = load_config_from_args()

    if args.test_whatsapp:
        logger.info("Enviando mensagem de teste para o WhatsApp via Twilio...")
        sample_offer = FlightOffer(
            airline="British Airways / LATAM (Teste)",
            price=5490.00,
            raw_price="R$ 5.490",
            departure_time="21/04/2027 23:15",
            arrival_time="22/04/2027 14:40",
            duration="11h 25m",
            stops=0,
            booking_url=build_google_flights_url(config),
        )
        msg = format_whatsapp_message(config, sample_offer, [sample_offer])
        send_whatsapp_alert(msg, dry_run=args.dry_run)
        sys.exit(0)

    if not args.loop:
        check_prices_and_notify(config, dry_run=args.dry_run)
        return

    # Modo monitoramento contínuo (--loop)
    logger.info(f"🔄 Iniciando monitoramento contínuo a cada {args.interval} minuto(s)... (Pressione Ctrl+C para parar)")
    try:
        while True:
            check_prices_and_notify(config, dry_run=args.dry_run)
            logger.info(f"💤 Aguardando {args.interval} minuto(s) até a próxima verificação...")
            time.sleep(args.interval * 60)
    except KeyboardInterrupt:
        logger.info("🛑 Monitoramento encerrado pelo usuário.")


if __name__ == "__main__":
    main()
